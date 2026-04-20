from __future__ import annotations

import json
from typing import Any

from diceflow.llm import LLMClient, narrate, parse_intent
from diceflow.models import TurnRecord
from diceflow.rules import RuleEngine
from diceflow.script import Script, load_script
from diceflow.state import GameState
from diceflow.updater import update_state
from diceflow.validator import validate


class Game:
    def __init__(self, script: Script | None = None, use_llm: bool = True) -> None:
        self.script = script or load_script("tomb_entrance")
        self.state = GameState(self.script)
        self.rules = RuleEngine()
        self.llm = self._build_llm() if use_llm else None

    def run_turn(self, player_input: str) -> TurnRecord:
        turn_id = self.state.advance_turn()
        action = parse_intent(player_input, self.state, self.llm)
        validation = validate(action, self.state)

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
        narration = narrate(action, check, changes, self.state, self.llm)
        summary = _make_summary(action, check, changes)

        record = TurnRecord(
            turn_id=turn_id,
            player_input=player_input,
            action=action,
            validation=validation,
            check=check,
            state_changes=changes,
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
    print(state.scene["description"])
    print(f"HP: {state.player['hp']}/{state.player['max_hp']}  物品: {'、'.join(state.player['inventory'])}")


def run_cli(script_name: str = "tomb_entrance", use_llm: bool = True, debug: bool = True) -> None:
    game = Game(script=load_script(script_name), use_llm=use_llm)
    print_intro(game.state)

    while not game.state.flags.get("game_over"):
        try:
            player_input = input(">> ").strip()
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
            print(
                "[debug] "
                + json.dumps(
                    {
                        "action": record.action,
                        "validation": record.validation,
                        "check": record.check,
                        "changes": record.state_changes,
                    },
                    ensure_ascii=False,
                )
            )
        print(record.narration)

    ending = game.state.flags.get("ending")
    if ending:
        print(_ending_text(ending))


def _make_summary(action: dict[str, Any], check: dict[str, Any], changes: dict[str, Any]) -> str:
    action_type = action.get("intent_family", "unknown")
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
