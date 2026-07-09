from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script
from diceflow.world_model.base import PhaseContext
from diceflow.world_model.favorability import FavorabilityPhase
from diceflow.world_model.schemas import get_favorability_config


def _ctx(state, *, action, resolution_kind="standard", turn_changes=None) -> PhaseContext:
    return PhaseContext(
        action=action, validation={"valid": True}, check={"result": "success"},
        turn_changes=turn_changes or {}, state=state, llm=None,
        lorebook=None, resolution_kind=resolution_kind,
    )


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


class FavorabilityPhaseHeuristicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_invalid_skips(self) -> None:
        ctx = _ctx(self.state, action={"type": "talk", "target_id": "barkeeper"},
                   resolution_kind="invalid")
        self.assertEqual(FavorabilityPhase().run(ctx), {})

    def test_existing_script_delta_recorded_no_extra_delta(self) -> None:
        # outcome table already gave +2 favorability and set disposition
        self.state.apply_changes({"entities": {"barkeeper": {"favorability_delta": 2}}})
        ctx = _ctx(self.state,
                   action={"type": "talk", "target_id": "barkeeper", "intent_family": "talk"},
                   turn_changes={"entities": {"barkeeper": {"favorability_delta": 2}}})
        out = FavorabilityPhase().run(ctx)
        self.assertNotIn("entities", out)  # no extra favorability_delta
        self.assertEqual(out["relationship_events"]["barkeeper"]["delta"], 2)

    def test_attack_lowers_favorability_via_heuristic(self) -> None:
        ctx = _ctx(self.state,
                   action={"type": "attack", "target_id": "barkeeper", "intent_family": "attack"},
                   turn_changes={"entities": {"barkeeper": {"hp_delta": -3}}})
        out = FavorabilityPhase().run(ctx)
        self.assertEqual(out["entities"]["barkeeper"]["favorability_delta"], -2)
        self.assertEqual(out["relationship_events"]["barkeeper"]["sentiment"], "negative")

    def test_threshold_cross_to_hostile(self) -> None:
        self.state.apply_changes({"set_entity_states": {"barkeeper": {"favorability": -4}}})
        ctx = _ctx(self.state,
                   action={"type": "attack", "target_id": "barkeeper", "intent_family": "attack"},
                   turn_changes={"entities": {"barkeeper": {"hp_delta": -3}}})
        out = FavorabilityPhase().run(ctx)
        # -4 + (-2) = -6 <= -5 -> hostile flip
        self.assertTrue(out["entities"]["barkeeper"].get("hostile"))
        self.assertEqual(out["entities"]["barkeeper"].get("disposition"), "hostile")
        self.assertIn("add_npc_memory", out)
        self.assertIn("events", out)

    def test_no_signal_no_change(self) -> None:
        ctx = _ctx(self.state,
                   action={"type": "inspect", "target_id": "barkeeper", "intent_family": "inspect"},
                   turn_changes={})
        self.assertEqual(FavorabilityPhase().run(ctx), {})


if __name__ == "__main__":
    unittest.main()
