from __future__ import annotations

import unittest
from typing import Any

from diceflow.core.models import Action
from diceflow.core.state import GameState
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script
from diceflow.app.game import Game
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase


def _ctx(state: GameState, *, action: dict, check: dict | None,
         resolution_kind: str, turn_changes: dict | None = None) -> PhaseContext:
    return PhaseContext(
        action=action, validation={"valid": True}, check=check,
        turn_changes=turn_changes or {}, state=state, llm=None,
        lorebook=None, resolution_kind=resolution_kind,
    )


class ReactionPhaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game_state = GameState(load_script("tomb_entrance"))
        self.attack = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        result = validate(self.attack, self.game_state)
        self.assertTrue(result["valid"])
        self.attack = result.get("_normalized_action", self.attack)
        # apply the attack so reaction has state to react to
        changes = update_state(self.attack, {"result": "success"}, self.game_state)
        self.game_state.apply_changes(changes)
        self.check = {"result": "success"}

    def test_standard_delegates_to_reaction_phase(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=self.check,
                   resolution_kind="standard", turn_changes={})
        out = phase.run(ctx)
        self.assertIn("player", out)
        self.assertEqual(out["player"]["hp_delta"], -2)

    def test_invalid_resolution_skips(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=self.check,
                   resolution_kind="invalid")
        self.assertEqual(phase.run(ctx), {})

    def test_transition_resolution_skips(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=self.check,
                   resolution_kind="transition_attempt")
        self.assertEqual(phase.run(ctx), {})

    def test_none_check_skips(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=None,
                   resolution_kind="standard")
        self.assertEqual(phase.run(ctx), {})


class _FakeOpenEndedLLM:
    narration_available = True

    def __init__(self, patch: dict[str, Any]) -> None:
        self.patch = patch
        self.call_count = 0

    def generate_open_ended_content(self, action, check, state, result_quality):
        self.call_count += 1
        return dict(self.patch)


class OpenEndedPhaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))
        self.action: Action = {
            "intent_family": "social", "type": "social", "target": "酒馆",
            "target_id": "", "tool": "", "tool_id": "", "approach_tags": [],
            "method_text": "在酒馆里看看有没有人愿意结伴同行",
            "method": "在酒馆里看看有没有人愿意结伴同行",
        }
        self.check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low",
                           "difficulty": "medium", "plausibility": "reasonable"},
        }

    def test_standard_delegates_to_open_ended(self) -> None:
        llm = _FakeOpenEndedLLM({"events": "一个旅人朝你点头。", "ops": []})
        phase = OpenEndedPhase()
        ctx = _ctx(self.state, action=self.action, check=self.check,
                   resolution_kind="standard", turn_changes={})
        ctx.llm = llm
        out = phase.run(ctx)
        self.assertEqual(llm.call_count, 1)
        self.assertIn("一个旅人朝你点头", out["events"][0])

    def test_invalid_resolution_skips(self) -> None:
        llm = _FakeOpenEndedLLM({"events": "nope", "ops": []})
        phase = OpenEndedPhase()
        ctx = _ctx(self.state, action=self.action, check=self.check,
                   resolution_kind="invalid")
        ctx.llm = llm
        self.assertEqual(phase.run(ctx), {})
        self.assertEqual(llm.call_count, 0)

    def test_transition_resolution_skips(self) -> None:
        llm = _FakeOpenEndedLLM({"events": "nope", "ops": []})
        phase = OpenEndedPhase()
        ctx = _ctx(self.state, action=self.action, check=self.check,
                   resolution_kind="transition_attempt")
        ctx.llm = llm
        self.assertEqual(phase.run(ctx), {})
        self.assertEqual(llm.call_count, 0)


class _SpyPhase:
    """Records whether it ran during a turn, regardless of branch."""
    name = "spy"
    order = 15  # between reaction(10) and open_ended(20)

    def __init__(self) -> None:
        self.ran_kinds: list[str] = []

    def run(self, ctx: PhaseContext) -> dict:
        self.ran_kinds.append(ctx.resolution_kind)
        return {}


class RunTurnRegistryTest(unittest.TestCase):
    def _game(self, script: str = "border_town_tavern") -> Game:
        return Game(script=load_script(script), use_llm=False)

    def test_standard_turn_runs_registered_phases(self) -> None:
        game = self._game()
        spy = _SpyPhase()
        game.phases.register(spy)
        game.run_turn("和老板攀谈")
        self.assertTrue(len(spy.ran_kinds) >= 1)

    def test_invalid_turn_still_invokes_registry(self) -> None:
        game = self._game()
        spy = _SpyPhase()
        game.phases.register(spy)
        game.run_turn("xyzqwerty 不存在的动作")
        # registry still ran the spy (uniform invocation across branches)
        self.assertTrue(len(spy.ran_kinds) >= 1)
        self.assertFalse(game.state.flags.get("game_over"))

    def test_existing_reaction_still_fires_in_combat(self) -> None:
        """Regression: a hostile target still counter-attacks after a hit."""
        game = self._game("tomb_entrance")
        hp_before = game.state.player["hp"]
        game.run_turn("攻击守卫", forced_roll=15)  # force non-crit success
        self.assertLess(game.state.player["hp"], hp_before)


if __name__ == "__main__":
    unittest.main()
