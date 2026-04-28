from __future__ import annotations

import logging
import sys
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
from diceflow.core.models import TurnRecord
from diceflow.core.npc_autonomy import npc_autonomy_phase, record_autonomy_turn
from diceflow.core.open_ended_content import open_ended_content_phase
from diceflow.core.reaction import merge_state_changes, reaction_phase
from diceflow.core.rules import RuleEngine
from diceflow.core.runtime_content import runtime_content_phase
from diceflow.core.state import GameState
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.llm.client import LLMClient, narrate, parse_intent
from diceflow.scripting.loader import Script, load_script


class Game:
    def __init__(self, script: Script, use_llm: bool = True) -> None:
        self.script = script
        self.state = GameState(self.script)
        self.rules = RuleEngine()
        self.adjudicator = DynamicAdjudicator()
        self.llm = self._build_llm() if use_llm else None

    def run_turn(self, player_input: str) -> TurnRecord:
        turn_id = self.state.advance_turn()
        action = parse_intent(player_input, self.state, self.llm)
        validation = validate(action, self.state)
        action = validation.pop("_normalized_action", action)
        validation.pop("_implied_spawn_applied", None)  # consumed by validate()

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
            # Light NPC autonomy after scene transition
            autonomy_changes = npc_autonomy_phase(action, check, world_changes, self.state, self.llm)
            if autonomy_changes:
                self.state.apply_changes(autonomy_changes)
                record_autonomy_turn(self.state, autonomy_changes)
            merged = merge_state_changes(world_changes, autonomy_changes)
            narration = narrate(action, check, merged, self.state, self.llm)
            summary = _make_summary(action, check, merged)
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
                state_changes=merged,
                narration=narration,
                summary=summary,
            )
            self.state.record_turn(record.to_dict())
            return record

        if self.adjudicator.can_adjudicate(action, validation, self.state):
            assessment = self.adjudicator.assess(action, self.state, self.llm)
            check = self.adjudicator.resolve(assessment)
            changes = self.adjudicator.update_state(action, check, self.state)
            open_ended_changes = open_ended_content_phase(action, check, changes, self.state, self.llm)
            if open_ended_changes:
                changes = _suppress_open_ended_fallback_spawn(changes, check, turn_id)
            self.state.apply_changes(changes)
            self.state.apply_changes(open_ended_changes)
            content_changes = runtime_content_phase(action, check, changes, self.state, self.llm)
            self.state.apply_changes(content_changes)
            reaction_changes = reaction_phase(action, check, changes, self.state)
            self.state.apply_changes(reaction_changes)
            autonomy_changes = npc_autonomy_phase(action, check, changes, self.state, self.llm)
            if autonomy_changes:
                self.state.apply_changes(autonomy_changes)
                record_autonomy_turn(self.state, autonomy_changes)
            turn_changes = merge_state_changes(changes, open_ended_changes, content_changes, reaction_changes, autonomy_changes)
            narration = narrate(action, check, turn_changes, self.state, self.llm)
            summary = _make_summary(action, check, turn_changes)
            dynamic_validation = {
                "valid": True,
                "reason": "dynamic_adjudication",
                "fallback_reason": validation.get("reason", ""),
            }
            record = TurnRecord(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation=dynamic_validation,
                check=check,
                state_changes=turn_changes,
                narration=narration,
                summary=summary,
            )
            self.state.record_turn(record.to_dict())
            return record

        if not validation["valid"]:
            changes = {
                "events": [
                    str(validation["reason"]),
                    str(self.script.get("invalid_action_event", "行动没有成立，但局势仍在推进。")),
                ],
            }
            self.state.apply_changes(changes)
            # Light NPC autonomy: the world doesn't stop when player hesitates
            autonomy_changes = npc_autonomy_phase(action, None, changes, self.state, self.llm)
            if autonomy_changes:
                self.state.apply_changes(autonomy_changes)
                record_autonomy_turn(self.state, autonomy_changes)
            merged = merge_state_changes(changes, autonomy_changes)
            narration_text = str(validation["reason"])
            if autonomy_changes.get("events"):
                narration_text += " " + " ".join(str(e) for e in autonomy_changes["events"])
            record = TurnRecord(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation=validation,
                check=None,
                state_changes=merged,
                narration=narration_text,
                summary=f"无效行动：{validation['reason']}",
            )
            self.state.record_turn(record.to_dict())
            return record

        check = self.rules.resolve(action, self.state)
        changes = update_state(action, check, self.state)
        self.state.apply_changes(changes)
        content_changes = runtime_content_phase(action, check, changes, self.state, self.llm)
        self.state.apply_changes(content_changes)
        reaction_changes = reaction_phase(action, check, changes, self.state)
        self.state.apply_changes(reaction_changes)
        autonomy_changes = npc_autonomy_phase(action, check, changes, self.state, self.llm)
        if autonomy_changes:
            self.state.apply_changes(autonomy_changes)
            record_autonomy_turn(self.state, autonomy_changes)
        turn_changes = merge_state_changes(changes, content_changes, reaction_changes, autonomy_changes)
        narration = narrate(action, check, turn_changes, self.state, self.llm)
        summary = _make_summary(action, check, turn_changes)

        record = TurnRecord(
            turn_id=turn_id,
            player_input=player_input,
            action=action,
            validation=validation,
            check=check,
            state_changes=turn_changes,
            narration=narration,
            summary=summary,
        )
        self.state.record_turn(record.to_dict())
        return record

    def _build_llm(self) -> LLMClient | None:
        try:
            return LLMClient()
        except Exception:
            logging.getLogger(__name__).warning("LLMClient init failed; falling back to no-LLM mode", exc_info=True)
            return None


def print_intro(state: GameState) -> None:
    print(state.script.get("intro", "DiceFlow MVP。输入 q/quit/退出 结束。"))


def run_cli(script_name: str = "tomb_entrance", use_llm: bool = True, debug: bool = True) -> None:
    game = Game(script=load_script(script_name), use_llm=use_llm)
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


def _suppress_open_ended_fallback_spawn(changes: dict[str, Any], check: dict[str, Any], turn_id: int) -> dict[str, Any]:
    """Remove the adjudicator's generic fallback spawn when LLM open-ended content
    has already filled the result with richer output.

    Only removes the spawn entries and runtime_script_patch that were created by
    ``_resolve_dynamic_spawn_from_script`` / ``_runtime_patch_for_spawn`` inside
    the adjudicator.  Any spawns or patches from other sources (LLM assessment,
    runtime generation) are left untouched.
    """
    assessment = check.get("assessment", {})
    intent_kind = str(assessment.get("intent_kind") or "") if isinstance(assessment, dict) else ""
    if intent_kind not in {"discover", "create_environment"} or "spawn_entities" not in changes:
        return changes

    fallback_patch_id = f"dynamic_spawn_turn_{turn_id}"
    patch = changes.get("runtime_script_patch")
    if isinstance(patch, dict) and patch.get("id") == fallback_patch_id:
        filtered = dict(changes)
        filtered.pop("runtime_script_patch", None)
    else:
        filtered = dict(changes)

    # The adjudicator's fallback spawn entities have two possible naming patterns:
    # 1. _resolve_dynamic_spawn_from_script creates: "dynamic_{kind}_{turn}" (e.g. dynamic_discover_5)
    # 2. _sanitize_spawn_spec wraps it as: "dynamic_dynamic_{kind}_{turn}"
    # We remove both, but keep any LLM-provided spawns (which have custom entity ids).
    fallback_suffix = f"{intent_kind}_{turn_id}"
    spawn = filtered.get("spawn_entities")
    if isinstance(spawn, dict):
        kept = {
            k: v for k, v in spawn.items()
            if not (str(k) == f"dynamic_{fallback_suffix}" or str(k) == f"dynamic_dynamic_{fallback_suffix}")
        }
        if kept:
            filtered["spawn_entities"] = kept
        else:
            filtered.pop("spawn_entities", None)

    return filtered


def _ending_text(ending: str) -> str:
    if ending == "victory":
        return "结局：胜利。"
    if ending == "death":
        return "结局：死亡。"
    if ending == "timeout":
        return "结局：20 轮耗尽。"
    return f"结局：{ending}。"
