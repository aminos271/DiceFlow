from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script
from diceflow.world_model.base import PhaseContext
from diceflow.world_model.schemas import get_time_config
from diceflow.world_model.time import TimePhase


def _ctx(state, *, action, resolution_kind, turn_changes=None) -> PhaseContext:
    return PhaseContext(
        action=action, validation={"valid": True}, check={"result": "success"},
        turn_changes=turn_changes or {}, state=state, llm=None,
        lorebook=None, resolution_kind=resolution_kind,
    )


class WorldClockStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("tomb_entrance"))

    def test_default_clock(self) -> None:
        self.assertEqual(self.state.world_clock["day"], 1)
        self.assertEqual(self.state.world_clock["segment"], "morning")
        self.assertEqual(self.state.world_clock["weather"], "")

    def test_set_clock_applies(self) -> None:
        self.state.apply_changes({"set_clock": {"day": 2, "segment": "night", "weather": "雨"}})
        self.assertEqual(self.state.world_clock["day"], 2)
        self.assertEqual(self.state.world_clock["segment"], "night")
        self.assertEqual(self.state.world_clock["weather"], "雨")

    def test_set_clock_partial_merge(self) -> None:
        self.state.apply_changes({"set_clock": {"segment": "evening"}})
        self.assertEqual(self.state.world_clock["segment"], "evening")
        self.assertEqual(self.state.world_clock["day"], 1)  # unchanged

    def test_advance_time_rolls_within_day(self) -> None:
        self.state.apply_changes({"advance_time": {"segments": 2}})
        # morning -> noon -> evening
        self.assertEqual(self.state.world_clock["segment"], "evening")
        self.assertEqual(self.state.world_clock["day"], 1)

    def test_advance_time_rolls_over_to_next_day(self) -> None:
        # default 5 segments: morning,noon,evening,night,deep_night
        self.state.apply_changes({"advance_time": {"segments": 5}})
        self.assertEqual(self.state.world_clock["day"], 2)
        self.assertEqual(self.state.world_clock["segment"], "morning")

    def test_snapshot_contains_world_clock(self) -> None:
        snap = self.state.get_snapshot()
        self.assertIn("world_clock", snap)
        self.assertEqual(snap["world_clock"]["segment"], "morning")


class TimeConfigTest(unittest.TestCase):
    def test_defaults_present(self) -> None:
        cfg = get_time_config(GameState(load_script("tomb_entrance")))
        self.assertIn("morning", cfg["segments"])
        self.assertEqual(cfg["magnitude_table"]["small"], 1)
        self.assertGreater(len(cfg["triggers"]), 0)

    def test_script_override(self) -> None:
        state = GameState(load_script("tomb_entrance"))
        state.script["world_model"] = {"time": {"segments": ["dawn", "dusk"]}}
        cfg = get_time_config(state)
        self.assertEqual(cfg["segments"], ["dawn", "dusk"])
        # non-overridden keys still fall back to defaults
        self.assertIn("magnitude_table", cfg)


class TimePhaseTriggerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("tomb_entrance"))

    def test_invalid_skips(self) -> None:
        ctx = _ctx(self.state, action={"type": "wait"}, resolution_kind="invalid")
        self.assertEqual(TimePhase().run(ctx), {})

    def test_wait_action_advances_one_segment(self) -> None:
        ctx = _ctx(self.state, action={"type": "wait", "method": "等待",
                                       "method_text": "等待"}, resolution_kind="standard")
        out = TimePhase().run(ctx)
        self.assertEqual(out["set_clock"]["segment"], "noon")
        self.assertIn("events", out)

    def test_transition_advances_one_segment(self) -> None:
        ctx = _ctx(self.state, action={"type": "move", "method_text": "进入通道"},
                   resolution_kind="transition_attempt")
        out = TimePhase().run(ctx)
        self.assertEqual(out["set_clock"]["segment"], "noon")

    def test_overnight_jumps_to_next_day_morning(self) -> None:
        self.state.apply_changes({"set_clock": {"day": 3, "segment": "night"}})
        ctx = _ctx(self.state, action={"type": "wait", "method_text": "在旅店过夜休息"},
                   resolution_kind="standard")
        out = TimePhase().run(ctx)
        self.assertEqual(out["set_clock"]["day"], 4)
        self.assertEqual(out["set_clock"]["segment"], "morning")

    def test_no_trigger_no_op(self) -> None:
        ctx = _ctx(self.state, action={"type": "attack", "method_text": "攻击守卫",
                                       "target_id": "guard_1"}, resolution_kind="standard")
        self.assertEqual(TimePhase().run(ctx), {})

    def test_segment_rollover_in_phase(self) -> None:
        self.state.apply_changes({"set_clock": {"segment": "deep_night"}})
        ctx = _ctx(self.state, action={"type": "wait", "method_text": "等待"},
                   resolution_kind="standard")
        out = TimePhase().run(ctx)
        # deep_night + 1 -> next day morning
        self.assertEqual(out["set_clock"]["day"], 2)
        self.assertEqual(out["set_clock"]["segment"], "morning")


class _FakeTimeLLM:
    narration_available = True

    def __init__(self, impact: str, reason: str = "闲谈良久") -> None:
        self.impact = impact
        self.reason = reason
        self.call_count = 0

    def judge_time_impact(self, action, state) -> dict:
        self.call_count += 1
        self.last_action = action
        return {"impact": self.impact, "reason": self.reason}


class TimePhaseLLMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("tomb_entrance"))

    def _ctx(self, action, llm) -> PhaseContext:
        ctx = _ctx(self.state, action=action, resolution_kind="standard")
        ctx.llm = llm
        return ctx

    def test_llm_medium_bucket_advances_two_segments(self) -> None:
        # default magnitude_table: medium=2
        llm = _FakeTimeLLM("medium")
        out = TimePhase().run(self._ctx(
            {"type": "talk", "method_text": "和老板长谈一宿往事"}, llm))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(out["set_clock"]["segment"], "evening")  # morning+2

    def test_llm_none_bucket_no_op(self) -> None:
        llm = _FakeTimeLLM("none")
        out = TimePhase().run(self._ctx(
            {"type": "talk", "method_text": "随口问好"}, llm))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(out, {})

    def test_script_trigger_takes_priority_over_llm(self) -> None:
        llm = _FakeTimeLLM("large")
        # wait is a scripted trigger -> LLM not consulted
        out = TimePhase().run(self._ctx(
            {"type": "wait", "method_text": "等待"}, llm))
        self.assertEqual(llm.call_count, 0)
        self.assertEqual(out["set_clock"]["segment"], "noon")

    def test_no_llm_no_trigger_no_op(self) -> None:
        ctx = _ctx(self.state,
                   action={"type": "talk", "method_text": "随口问好"},
                   resolution_kind="standard")
        ctx.llm = None
        self.assertEqual(TimePhase().run(ctx), {})


from diceflow.app.game import Game


class TimeIntegrationTest(unittest.TestCase):
    def test_wait_turn_advances_clock(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        self.assertEqual(game.state.world_clock["segment"], "morning")
        game.run_turn("等待")
        self.assertEqual(game.state.world_clock["segment"], "noon")
        self.assertIn("world_clock", game.state.get_snapshot())

    def test_attack_does_not_advance_time(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        before = dict(game.state.world_clock)
        game.run_turn("攻击守卫", forced_roll=15)
        self.assertEqual(game.state.world_clock, before)


if __name__ == "__main__":
    unittest.main()
