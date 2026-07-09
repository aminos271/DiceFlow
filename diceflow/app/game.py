from __future__ import annotations

import logging
import sys
from copy import deepcopy
from typing import Any

from diceflow.app.ui import (
    render_action_hints,
    render_debug,
    render_help_panel,
    render_inventory_panel,
    render_meta_result,
    render_prompt,
    render_scene_panel,
    render_status_panel,
    render_turn_result,
)

META_LOOK = frozenset({"look", "l", "看", "观察", "环顾", "查看", "环视"})
META_INV = frozenset({"inv", "inventory", "i", "背包", "物品", "道具", "装备"})
META_STATUS = frozenset({"status", "st", "状态", "血量", "生命"})
META_HELP = frozenset({"help", "h", "?", "？", "帮助", "说明", "指令"})
META_HINT = frozenset({"hint", "提示", "线索", "建议", "行动"})
from diceflow.core.adjudicator import DynamicAdjudicator
from diceflow.core.dynamic_world import dynamic_world_phase
from diceflow.core.models import TurnRecord, TurnResolution
from diceflow.core.npc_autonomy import NPC_AUTONOMY_ENABLED, npc_autonomy_phase, record_autonomy_turn
from diceflow.core.reaction import merge_state_changes
from diceflow.core.rules import RuleEngine
from diceflow.core.state import GameState
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.llm.client import LLMClient, narrate, parse_intent
from diceflow.core.bootstrap import WorldBootstrap
from diceflow.scripting.loader import Script, load_script
from diceflow.world_model import PhaseContext, PhaseRegistry
from diceflow.world_model.favorability import FavorabilityPhase
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase
from diceflow.world_model.time import TimePhase


class Game:
    def __init__(self, script: Script | WorldBootstrap, use_llm: bool = True, lorebook: Any | None = None) -> None:
        if isinstance(script, WorldBootstrap):
            script = script.to_script_dict()
        self.script = script
        self.state = GameState(self.script)
        self.rules = RuleEngine()
        self.adjudicator = DynamicAdjudicator()
        self.llm = self._build_llm() if use_llm else None
        self.lorebook = lorebook  # SessionLore | None, set by web layer
        self.phases = PhaseRegistry()
        self.phases.register(ReactionPhase())
        self.phases.register(OpenEndedPhase())
        self.phases.register(TimePhase())
        self.phases.register(FavorabilityPhase())

    def run_turn(self, player_input: str, forced_roll: int | None = None) -> TurnRecord:
        turn_id = self.state.advance_turn()
        before_context = _presentation_context(self.state)
        action = parse_intent(player_input, self.state, self.llm)
        action.setdefault("raw_input", player_input)
        if not str(action.get("method_text") or "").strip():
            action["method_text"] = player_input
        if not str(action.get("method") or "").strip():
            action["method"] = player_input
        validation = validate(action, self.state)
        action = validation.pop("_normalized_action", action)
        validation.pop("_implied_spawn_applied", None)  # consumed by validate()
        self.state.note_player_interaction(action)

        # ── Branch: Dynamic world transition ────────────────────────
        world_changes = dynamic_world_phase(action, validation, self.state, self.llm)
        if world_changes:
            check = {
                "dc": 0,
                "roll": 0,
                "result": "success",
                "dynamic": True,
                "assessment": {"intent_kind": "transition"},
            }
            self.state.apply_changes(world_changes)
            turn_changes = self._run_post_resolution(
                turn_id, player_input, action, validation, check, world_changes,
                "transition_attempt",
            )
            turn_resolution = build_turn_resolution(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation={"valid": True, "reason": "dynamic_world", "fallback_reason": validation.get("reason", "")},
                check=check,
                state_changes=turn_changes,
                resolution_kind="transition_attempt",
                reason_tags=["world_transition_attempt"],
                state=self.state,
                lorebook=self.lorebook,
            )
            narration_text = narrate(turn_resolution, self.state, self.llm)
            summary = _make_summary(action, check, turn_changes)
            record = TurnRecord(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation={
                    "valid": True,
                    "reason": "dynamic_world",
                    "fallback_reason": validation.get("reason", ""),
                },
                check=check,
                state_changes=turn_changes,
                narration=narration_text,
                summary=summary,
            )
            _attach_turn_presentation(record, before_context, self.state)
            self.state.record_turn(record.to_dict())
            return record

        # ── Branch: Dynamic adjudication ────────────────────────────
        if self.adjudicator.can_adjudicate(action, validation, self.state):
            assessment = self.adjudicator.assess(action, self.state, self.llm)
            check = self.adjudicator.resolve(assessment, forced_roll=forced_roll)
            changes = self.adjudicator.update_state(action, check, self.state)
            self.state.apply_changes(changes)
            turn_changes = self._run_post_resolution(
                turn_id, player_input, action, validation, check, changes,
                "dynamic_adjudication",
            )
            reason_tags = list(assessment.get("reason_tags", []))
            turn_resolution = build_turn_resolution(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation={"valid": True, "reason": "dynamic_adjudication", "fallback_reason": validation.get("reason", "")},
                check=check,
                state_changes=turn_changes,
                resolution_kind="dynamic_adjudication",
                reason_tags=reason_tags,
                state=self.state,
                lorebook=self.lorebook,
            )
            narration_text = narrate(turn_resolution, self.state, self.llm)
            summary = _make_summary(action, check, turn_changes)
            record = TurnRecord(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation={
                    "valid": True,
                    "reason": "dynamic_adjudication",
                    "fallback_reason": validation.get("reason", ""),
                },
                check=check,
                state_changes=turn_changes,
                narration=narration_text,
                summary=summary,
            )
            _attach_turn_presentation(record, before_context, self.state)
            self.state.record_turn(record.to_dict())
            return record

        # ── Branch: Invalid action ──────────────────────────────────
        if not validation["valid"]:
            changes = {
                "events": [
                    str(validation["reason"]),
                    str(self.script.get("invalid_action_event", "行动没有成立，但局势仍在推进。")),
                ],
            }
            self.state.apply_changes(changes)
            turn_changes = self._run_post_resolution(
                turn_id, player_input, action, validation, None, changes,
                "invalid",
            )
            turn_resolution = build_turn_resolution(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation=validation,
                check=None,
                state_changes=turn_changes,
                resolution_kind="invalid",
                reason_tags=[],
                state=self.state,
                lorebook=self.lorebook,
            )
            narration_text = narrate(turn_resolution, self.state, self.llm)
            record = TurnRecord(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation=validation,
                check=None,
                state_changes=turn_changes,
                narration=narration_text,
                summary=f"无效行动：{validation['reason']}",
            )
            _attach_turn_presentation(record, before_context, self.state)
            self.state.record_turn(record.to_dict())
            return record

        # ── Branch: Standard resolution ─────────────────────────────
        check = self.rules.resolve(action, self.state, forced_roll=forced_roll)
        changes = update_state(action, check, self.state)
        self.state.apply_changes(changes)
        turn_changes = self._run_post_resolution(
            turn_id, player_input, action, validation, check, changes,
            "standard",
        )
        turn_resolution = build_turn_resolution(
            turn_id=turn_id,
            player_input=player_input,
            action=action,
            validation=validation,
            check=check,
            state_changes=turn_changes,
            resolution_kind="standard",
            reason_tags=[],
            state=self.state,
            lorebook=self.lorebook,
        )
        narration_text = narrate(turn_resolution, self.state, self.llm)
        summary = _make_summary(action, check, turn_changes)

        record = TurnRecord(
            turn_id=turn_id,
            player_input=player_input,
            action=action,
            validation=validation,
            check=check,
            state_changes=turn_changes,
            narration=narration_text,
            summary=summary,
        )
        _attach_turn_presentation(record, before_context, self.state)
        self.state.record_turn(record.to_dict())
        return record

    def _run_post_resolution(
        self,
        turn_id: int,
        player_input: str,
        action: dict[str, Any],
        validation: dict[str, Any],
        check: dict[str, Any] | None,
        turn_changes: dict[str, Any],
        resolution_kind: str,
    ) -> dict[str, Any]:
        """Run the registered post-resolution phase chain uniformly.

        Replaces the per-branch reaction→open_ended calls. Each phase self-
        decides whether to apply based on resolution_kind, preserving the
        pre-refactor skip semantics for invalid/transition branches.
        """
        del player_input  # reserved for future phases; not used by default phases
        ctx = PhaseContext(
            action=action,
            validation=validation,
            check=check,
            turn_changes=dict(turn_changes),
            state=self.state,
            llm=self.llm,
            lorebook=self.lorebook,
            resolution_kind=resolution_kind,
        )
        phase_changes = self.phases.run_all(ctx)
        if resolution_kind in {"standard", "dynamic_adjudication"}:
            _sync_lorebook_for_patch(self.lorebook, ctx.turn_changes, turn_id)
        return merge_state_changes(turn_changes, phase_changes)

    def _build_llm(self) -> LLMClient | None:
        try:
            return LLMClient()
        except Exception:
            logging.getLogger(__name__).warning("LLMClient init failed; falling back to no-LLM mode", exc_info=True)
            return None


def print_intro(state: GameState) -> None:
    print(state.script.get("intro", "DiceFlow MVP。输入 q/quit/退出 结束。"))


def run_cli(script_name: str | None = None, world_id: str | None = None, use_llm: bool = True, debug: bool = True) -> None:
    if script_name:
        raise ValueError("script-driven CLI mode has been removed; use --world")
    if world_id:
        from diceflow.core.bootstrap import bootstrap_from_defaults, bootstrap_from_lorebook
        from diceflow.core.lorebook import SessionLore
        lorebook = SessionLore()
        lorebook.seed_from_world_content_for_id(world_id)
        bootstrap = bootstrap_from_lorebook(lorebook, world_id) or bootstrap_from_defaults(world_id)
        game = Game(script=bootstrap, use_llm=use_llm, lorebook=lorebook)
    else:
        # Default: bootstrap from the default world
        from diceflow.core.bootstrap import bootstrap_from_defaults
        game = Game(script=bootstrap_from_defaults("_default"), use_llm=use_llm)
    print_intro(game.state)

    while not game.state.flags.get("game_over"):
        print(render_status_panel(game.state))
        print(render_scene_panel(game.state))
        print(render_action_hints(game.state))
        try:
            player_input = input(render_prompt()).strip()
        except EOFError:
            print("输入结束，游戏结束。")
            break
        if player_input.lower() in {"q", "quit", "exit"} or player_input == "退出":
            print("游戏结束。")
            break
        if not player_input:
            continue

        meta_result = _handle_meta(player_input, game)
        if meta_result is not None:
            print(meta_result)
            continue

        record = game.run_turn(player_input)
        if debug:
            print(render_debug(record), file=sys.stderr)
        print(render_turn_result(record))

    ending = game.state.flags.get("ending")
    if ending:
        print(_ending_text(ending))


def _handle_meta(player_input: str, game: Game) -> str | None:
    """Handle meta-commands that don't consume a turn. Returns rendered output or None."""
    inp = player_input.strip().lower()
    if inp in META_HELP:
        return render_help_panel()
    if inp in META_LOOK:
        return render_meta_result("你环顾四周。") + "\n" + render_scene_panel(game.state)
    if inp in META_INV:
        return render_inventory_panel(game.state)
    if inp in META_STATUS:
        return render_status_panel(game.state)
    if inp in META_HINT:
        return render_action_hints(game.state)
    return None


def build_turn_resolution(
    turn_id: int,
    player_input: str,
    action: dict[str, Any],
    validation: dict[str, Any],
    check: dict[str, Any] | None,
    state_changes: dict[str, Any],
    resolution_kind: str,
    reason_tags: list[str],
    state: GameState,
    lorebook: Any | None = None,
) -> TurnResolution:
    visible_npcs = _visible_npcs_for_narration(state)
    lorebook_context = _lorebook_context(lorebook) if lorebook else {}
    return TurnResolution(
        turn_id=turn_id,
        player_input=player_input,
        action=action,
        validation=validation,
        check=check,
        state_changes=state_changes,
        resolution_kind=resolution_kind,
        reason_tags=reason_tags,
        visible_npcs=visible_npcs,
        recent_events=list(state.recent_events[-10:]),
        recent_history=[
            {
                "turn_id": int(item.get("turn_id", 0)),
                "player_input": str(item.get("player_input") or ""),
                "summary": str(item.get("summary") or ""),
            }
            for item in state.history[-3:]
            if isinstance(item, dict)
        ],
        scene=state.get_current_scene(),
        player_state=dict(state.player),
        world_clock=deepcopy(state.world_clock),
        **lorebook_context,  # type: ignore[typeddict-item]
    )


def _lorebook_context(lorebook: Any) -> dict[str, Any]:
    """Extract lorebook entries for inclusion in turn_resolution."""
    if lorebook is None:
        return {"lorebook_entries": []}
    try:
        entries = []
        for entry in lorebook.all_entries():
            entries.append({
                "type": entry.type,
                "title": entry.title,
                "summary": entry.summary,
                "tags": entry.tags,
                "linked_entity_id": entry.linked_entity_id,
            })
        return {"lorebook_entries": entries}
    except Exception:
        return {"lorebook_entries": []}


def _sync_lorebook_for_patch(
    lorebook: Any,
    open_ended_changes: dict[str, Any],
    turn_id: int,
) -> None:
    """Sync generated entities (NPCs, clues) from a content patch to lorebook."""
    if lorebook is None:
        return
    patch = open_ended_changes.get("runtime_script_patch")
    if not isinstance(patch, dict):
        return
    for op in patch.get("ops", []):
        if not isinstance(op, dict):
            continue
        if op.get("op") != "add_entity":
            continue
        entity = op.get("entity")
        if not isinstance(entity, dict):
            continue
        entity_type = str(entity.get("type") or "")
        tags = [str(t) for t in entity.get("tags", [])]
        name = str(entity.get("name") or op.get("id") or "unknown")
        entity_id = str(op.get("id") or "")

        if entity_type == "npc" or "npc" in tags:
            lorebook.create_entry(
                type="character",
                title=name,
                summary=f"运行时生成的NPC：{name}",
                tags=["derived", "character", "generated"],
                source="derived",
                linked_entity_id=entity_id,
                linked_turn_ids=[turn_id],
                discovered=True,
            )
        elif entity_type in {"clue", "pickup", "item"} or "clue" in tags:
            lorebook.create_entry(
                type="event",
                title=f"发现：{name}",
                summary=f"在第{turn_id}回合发现了{name}。",
                tags=["derived", "clue", "generated"],
                source="derived",
                linked_entity_id=entity_id,
                linked_turn_ids=[turn_id],
                discovered=True,
            )


def _visible_npcs_for_narration(state: GameState) -> dict[str, dict[str, Any]]:
    """Return visible NPC data suitable for narrator consumption."""
    npcs: dict[str, dict[str, Any]] = {}
    for eid, ent in state.get_visible_entities().items():
        if ent.get("type") == "npc" or "npc" in ent.get("tags", []):
            if ent.get("alive", True) and ent.get("available", True):
                npc_data: dict[str, Any] = {
                    "name": ent.get("name", eid),
                    "disposition": ent.get("disposition", "neutral"),
                    "favorability": ent.get("favorability", 0),
                    "hostile": bool(ent.get("hostile") or "hostile" in ent.get("tags", [])),
                }
                personality = ent.get("personality")
                if isinstance(personality, dict):
                    npc_data["personality"] = {
                        "traits": personality.get("traits", []),
                        "manner": personality.get("manner", ""),
                    }
                memories = state.get_memories_for_npc(eid)
                if memories:
                    npc_data["recent_memories"] = memories[:5]
                npcs[eid] = npc_data
    return npcs


def _make_summary(action: dict[str, Any], check: dict[str, Any], changes: dict[str, Any]) -> str:
    action_type = action.get("intent_family", "unknown")
    if check.get("dynamic"):
        assessment = check.get("assessment", {})
        intent_kind = "improvised"
        if isinstance(assessment, dict):
            intent_kind = str(assessment.get("intent_kind") or intent_kind)
        action_type = f"dynamic:{intent_kind}"
    target = action.get("target") or action.get("target_id") or "当前局势"
    result = check.get("result", "unknown")
    event = "；".join(changes.get("events", []))
    return f"{action_type} {target} -> {result}。{event}"


def _presentation_context(state: GameState) -> dict[str, Any]:
    return {
        "player_hp": int(state.player.get("hp", 0)),
        "hostile_count": len(state.get_hostile_entities()),
        "entities": {
            entity_id: {
                "name": str(entity.get("name") or entity_id),
                "hp": entity.get("hp"),
                "alive": bool(entity.get("alive", True)),
                "hostile": bool(entity.get("hostile") or "hostile" in entity.get("tags", [])),
                "visible": bool(entity.get("visible", True)),
                "available": bool(entity.get("available", True)),
                "locked": bool(entity.get("locked")),
                "opened": bool(entity.get("opened")),
            }
            for entity_id, entity in state.entities.items()
        },
    }


def _attach_turn_presentation(record: TurnRecord, before: dict[str, Any], state: GameState) -> None:
    after = _presentation_context(state)
    record.mechanical_results = _mechanical_results(record, before, after, state)
    record.resolution_card = _combat_resolution_card(record, before, after, state)


def _mechanical_results(
    record: TurnRecord,
    before: dict[str, Any],
    after: dict[str, Any],
    state: GameState,
) -> list[str]:
    check = record.check or {}
    changes = record.state_changes or {}
    lines: list[str] = []

    entity_changes = changes.get("entities", {}) if isinstance(changes.get("entities"), dict) else {}
    set_entity_states = changes.get("set_entity_states", {}) if isinstance(changes.get("set_entity_states"), dict) else {}
    touched_entities = set(entity_changes) | set(set_entity_states)

    for entity_id in touched_entities:
        ent_before = before.get("entities", {}).get(entity_id, {})
        ent_after = after.get("entities", {}).get(entity_id, ent_before)
        name = str(ent_after.get("name") or ent_before.get("name") or entity_id)
        delta = 0
        raw_changes = {}
        if isinstance(entity_changes.get(entity_id), dict):
            raw_changes.update(entity_changes[entity_id])
        if isinstance(set_entity_states.get(entity_id), dict):
            raw_changes.update(set_entity_states[entity_id])
        if isinstance(raw_changes.get("hp_delta"), (int, float)):
            delta = int(raw_changes["hp_delta"])
        before_hp = ent_before.get("hp")
        after_hp = ent_after.get("hp")
        if before_hp is not None and after_hp is not None and before_hp != after_hp:
            hp_change = int(before_hp) - int(after_hp)
            if delta < 0:
                lines.append(f"造成 {max(1, hp_change)} 点伤害")
            elif delta > 0:
                lines.append(f"{name} 恢复 {abs(hp_change)} 点生命")
            lines.append(f"{name} HP：{before_hp} -> {after_hp}")
        before_alive = bool(ent_before.get("alive", True))
        after_alive = bool(ent_after.get("alive", True))
        if before_alive and not after_alive:
            lines.append(f"{name}死亡")
        if ent_before.get("visible") is False and ent_after.get("visible") is True:
            lines.append(f"发现：{name}")
        if ent_before.get("locked") is True and ent_after.get("locked") is False:
            lines.append(f"{name}解锁")
        if ent_before.get("opened") is False and ent_after.get("opened") is True:
            lines.append(f"{name}打开")

    player_changes = changes.get("player", {}) if isinstance(changes.get("player"), dict) else {}
    hp_delta = player_changes.get("hp_delta")
    if isinstance(hp_delta, (int, float)) and hp_delta:
        before_hp = before.get("player_hp")
        after_hp = after.get("player_hp")
        if hp_delta < 0:
            lines.append(f"你受到 {abs(int(hp_delta))} 点伤害")
        else:
            lines.append(f"你恢复 {int(hp_delta)} 点生命")
        lines.append(f"你的 HP：{before_hp} -> {after_hp}")

    spawns = changes.get("spawn_entities", {}) if isinstance(changes.get("spawn_entities"), dict) else {}
    if spawns:
        names = [str(entity.get("name") or entity_id) for entity_id, entity in spawns.items() if isinstance(entity, dict)]
        if names:
            lines.append(f"新增实体：{'、'.join(names)}")

    moved = changes.get("move_item_to_inventory", [])
    if isinstance(moved, list) and moved:
        names = [_entity_name(str(entity_id), state) for entity_id in moved]
        lines.append(f"获得：{'、'.join(names)}")

    if before.get("hostile_count") != after.get("hostile_count"):
        lines.append(f"威胁：{before.get('hostile_count')} -> {after.get('hostile_count')}")

    if not lines and check:
        result = check.get("result", "unknown")
        lines.append(f"行动判定结果：{result}")
    return lines


def _combat_resolution_card(
    record: TurnRecord,
    before: dict[str, Any],
    after: dict[str, Any],
    state: GameState,
) -> dict[str, Any] | None:
    if before.get("hostile_count", 0) <= 0 or after.get("hostile_count", 0) != 0:
        return None

    defeated = [
        ent_after.get("name") or entity_id
        for entity_id, ent_after in after.get("entities", {}).items()
        if before.get("entities", {}).get(entity_id, {}).get("hostile")
        and before.get("entities", {}).get(entity_id, {}).get("alive", True)
        and not ent_after.get("alive", True)
    ]
    if not defeated:
        return None

    return {
        "type": "combat_end",
        "title": "⚔️ 战斗结束",
        "outcome": f"{'、'.join(str(name) for name in defeated)}死亡。",
        "threat_before": before.get("hostile_count", 0),
        "threat_after": after.get("hostile_count", 0),
        "scene_changes": _scene_change_lines(record, state),
        "available_actions": _post_combat_actions(state),
    }


def _scene_change_lines(record: TurnRecord, state: GameState) -> list[str]:
    changes = record.state_changes or {}
    lines: list[str] = []
    spawns = changes.get("spawn_entities", {}) if isinstance(changes.get("spawn_entities"), dict) else {}
    for entity_id, entity in spawns.items():
        if not isinstance(entity, dict):
            continue
        name = str(entity.get("name") or entity_id)
        if entity.get("type") == "corpse" or "corpse" in entity.get("tags", []):
            lines.append(f"{name}倒在门前")
        else:
            lines.append(f"{name}出现在场景中")
    for entity_id, ent in state.get_visible_entities().items():
        name = str(ent.get("name") or entity_id)
        if ent.get("type") == "item" or "equipment" in ent.get("tags", []):
            lines.append(f"{name}掉落在地")
        if ent.get("locked"):
            lines.append(f"{name}仍然锁着")
    scene_desc = str(state.get_current_scene().get("description", ""))
    if "冷光" in scene_desc and not any("冷光" in line for line in lines):
        lines.append("门缝里透出冷光")
    return _dedupe(lines)[:5]


def _post_combat_actions(state: GameState) -> list[str]:
    actions: list[str] = []
    visible = state.get_visible_entities()
    for _, ent in visible.items():
        name = str(ent.get("name") or "目标")
        tags = set(str(tag) for tag in ent.get("tags", []))
        if ent.get("type") == "corpse" or "corpse" in tags:
            actions.append(f"搜索{name}")
        elif ent.get("type") in {"item", "pickup"} or "equipment" in tags:
            actions.append(f"捡起{name}")
        elif ent.get("type") == "door" or "door" in tags:
            actions.append(f"检查{name}")
    for item in state.get_inventory_items():
        if "火把" in item:
            actions.append("拿火把")
    return _dedupe(actions)[:6]


def _entity_name(entity_id: str, state: GameState) -> str:
    entity = state.entities.get(entity_id)
    if isinstance(entity, dict):
        return str(entity.get("name") or entity_id)
    return entity_id


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _ending_text(ending: str) -> str:
    if ending == "victory":
        return "结局：胜利。"
    if ending == "death":
        return "结局：死亡。"
    if ending == "timeout":
        return "结局：20 轮耗尽。"
    return f"结局：{ending}。"
