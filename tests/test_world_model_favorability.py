from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script
from diceflow.world_model.schemas import get_favorability_config


class RelationshipEventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_relationship_events_appends_history(self) -> None:
        self.state.apply_changes({"relationship_events": {
            "barkeeper": {"delta": 2, "reason": "攀谈甚欢", "sentiment": "positive", "turn_id": 1},
        }})
        rel = self.state.entities["barkeeper"]["relationship"]
        self.assertEqual(len(rel["history"]), 1)
        self.assertEqual(rel["history"][0]["delta"], 2)
        self.assertEqual(rel["history"][0]["sentiment"], "positive")

    def test_relationship_events_lazy_inits(self) -> None:
        self.assertNotIn("relationship", self.state.entities["barkeeper"])
        self.state.apply_changes({"relationship_events": {
            "barkeeper": {"delta": -1, "reason": "x", "sentiment": "negative", "turn_id": 2},
        }})
        self.assertIn("relationship", self.state.entities["barkeeper"])

    def test_relationship_events_unknown_entity_ignored(self) -> None:
        before = dict(self.state.entities)
        self.state.apply_changes({"relationship_events": {
            "no_such_npc": {"delta": 1, "reason": "x", "sentiment": "positive", "turn_id": 1},
        }})
        self.assertEqual(self.state.entities, before)

    def test_history_capped(self) -> None:
        for i in range(25):
            self.state.apply_changes({"relationship_events": {
                "barkeeper": {"delta": 1, "reason": "x", "sentiment": "positive", "turn_id": i},
            }})
        self.assertEqual(len(self.state.entities["barkeeper"]["relationship"]["history"]), 20)


class FavorabilityConfigTest(unittest.TestCase):
    def test_defaults_present(self) -> None:
        cfg = get_favorability_config(GameState(load_script("border_town_tavern")))
        self.assertEqual(cfg["magnitude_table"]["medium"], 2)
        self.assertGreater(len(cfg["thresholds"]), 0)

    def test_override(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        state.script["world_model"] = {"favorability": {"magnitude_table": {"small": 2, "medium": 4, "large": 6}}}
        cfg = get_favorability_config(state)
        self.assertEqual(cfg["magnitude_table"]["medium"], 4)
        self.assertIn("thresholds", cfg)  # fallback for non-overridden keys


if __name__ == "__main__":
    unittest.main()
