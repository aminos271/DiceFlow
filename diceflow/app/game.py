from __future__ import annotations

import sys
from typing import Any

from diceflow.app.ui import (
    render_action_hints,
    render_debug,
    render_prompt,
    render_scene_panel,
    render_status_panel,
    render_turn_result,
)
from diceflow.core.adjudicator import DynamicAdjudicator
from diceflow.core.dynamic_world import dynamic_world_phase
from diceflow.core.models import TurnRecord
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
            narration = narrate(action, check, world_changes, self.state, self.llm)
            summary = _make_summary(action, check, world_changes)
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
                state_changes=world_changes,
                narration=narration,
                summary=summary,
            )
            self.state.record_turn(record.to_dict())
            return record

        if self.adjudicator.can_adjudicate(action, validation, self.state):
            assessment = self.adjudicator.assess(action, self.state, self.llm)
            check = self.adjudicator.resolve(assessment)
            changes = self.adjudicator.update_state(action, check, self.state)
            self.state.apply_changes(changes)
            content_changes = runtime_content_phase(action, check, changes, self.state, self.llm)
            self.state.apply_changes(content_changes)
            reaction_changes = reaction_phase(action, check, changes, self.state)
            self.state.apply_changes(reaction_changes)
            turn_changes = merge_state_changes(changes, content_changes, reaction_changes)
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
            record = TurnRecord(
                turn_id=turn_id,
                player_input=player_input,
                action=action,
                validation=validation,
                check=None,
                state_changes=changes,
                narration=str(validation["reason"]),
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
        turn_changes = merge_state_changes(changes, content_changes, reaction_changes)
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

        record = game.run_turn(player_input)
        if debug:
            print(render_debug(record), file=sys.stderr)
        print(render_turn_result(record))

    ending = game.state.flags.get("ending")
    if ending:
        print(_ending_text(ending))


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


def _ending_text(ending: str) -> str:
    if ending == "victory":
        return "结局：胜利。"
    if ending == "death":
        return "结局：死亡。"
    if ending == "timeout":
        return "结局：20 轮耗尽。"
    return f"结局：{ending}。"
