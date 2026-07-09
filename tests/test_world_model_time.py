from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script
from diceflow.world_model.schemas import get_time_config


class WorldClockStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

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
        cfg = get_time_config(GameState(load_script("border_town_tavern")))
        self.assertIn("morning", cfg["segments"])
        self.assertEqual(cfg["magnitude_table"]["small"], 1)
        self.assertGreater(len(cfg["triggers"]), 0)

    def test_script_override(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        state.script["world_model"] = {"time": {"segments": ["dawn", "dusk"]}}
        cfg = get_time_config(state)
        self.assertEqual(cfg["segments"], ["dawn", "dusk"])
        # non-overridden keys still fall back to defaults
        self.assertIn("magnitude_table", cfg)


if __name__ == "__main__":
    unittest.main()
