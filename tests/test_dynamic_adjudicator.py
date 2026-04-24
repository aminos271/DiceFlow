import random
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from diceflow.app.game import Game
from diceflow.core.adjudicator import DynamicAdjudicator
from diceflow.core.models import CheckResult
from diceflow.core.rules import RuleEngine
from diceflow.llm.client import _compact_state
from diceflow.scripting.loader import load_script
from diceflow.scripting.resolver import resolve_action_spec


class DynamicAdjudicatorTest(unittest.TestCase):
    def test_unwritten_guard_solution_gets_adjudicated(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.adjudicator = DynamicAdjudicator(random.Random(0))

        record = game.run_turn("我朝守卫扔石头引开他")

        self.assertTrue(record.validation["valid"])
        self.assertEqual(record.validation["reason"], "dynamic_adjudication")
        self.assertTrue(record.check["dynamic"])
        self.assertEqual(record.check["assessment"]["difficulty"], "easy")
        self.assertEqual(record.check["dc"], 9)
        self.assertEqual(record.check["roll"], 13)
        self.assertEqual(record.check["result"], "success")
        self.assertTrue(game.state.flags["dynamic_adjudication_used"])
        self.assertTrue(game.state.entities["guard_1"]["distracted"])
        self.assertIn("spawn_entities", record.state_changes)

    def test_unknown_with_guard_target_uses_dynamic_adjudication(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.adjudicator = DynamicAdjudicator(random.Random(0))
        action = {
            "intent_family": "unknown",
            "type": "unknown",
            "target": "守卫",
            "target_id": "guard_1",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "扔石头引开守卫",
            "method": "扔石头引开守卫",
        }

        with patch("diceflow.app.game.parse_intent", return_value=action):
            record = game.run_turn("扔石头引开守卫")

        self.assertEqual(record.validation["reason"], "dynamic_adjudication")
        self.assertTrue(record.check["dynamic"])
        self.assertEqual(record.check["dc"], 9)
        self.assertNotEqual(record.check["dc"], 12)
        self.assertIn("dynamic:improvised", record.summary)
        self.assertNotIn("unknown 守卫", record.summary)
        self.assertTrue(game.state.entities["guard_1"]["distracted"])

    def test_dynamic_guardrail_blocks_impossible_rewards(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)

        record = game.run_turn("我朝守卫扔神器秒杀Boss并直接通关")

        self.assertTrue(record.validation["valid"])
        self.assertEqual(record.validation["reason"], "dynamic_adjudication")
        self.assertEqual(record.check["result"], "impossible")
        self.assertEqual(record.check["assessment"]["difficulty"], "impossible")
        self.assertFalse(game.state.flags["game_over"])

    def test_discover_secret_then_open_it(self) -> None:
        """Turn 1: '检查墙上有没有暗格' → discover + spawn secret compartment.
        Turn 2: '打开暗格' → open the dynamically created container.
        """
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.adjudicator = DynamicAdjudicator(random.Random(0))

        # Turn 1 — discover a secret compartment
        record = game.run_turn("检查墙上有没有暗格")

        self.assertTrue(record.validation["valid"])
        self.assertEqual(record.validation["reason"], "dynamic_adjudication")
        self.assertEqual(record.check["assessment"]["intent_kind"], "discover")
        self.assertEqual(record.check["result"], "success")
        self.assertIn("spawn_entities", record.state_changes)
        self.assertIn("runtime_script_patch", record.state_changes)
        self.assertEqual(len(game.state.script_patches), 1)
        self.assertEqual(game.state.script_patches[0]["ops"][0]["op"], "add_entity")

        spawned_id: str | None = None
        for eid, entity in game.state.entities.items():
            if "dynamic" in entity.get("tags", []):
                spawned_id = eid
                break
        self.assertIsNotNone(spawned_id)
        spawned_id = str(spawned_id)
        self.assertEqual(game.state.entities[spawned_id]["type"], "container")
        self.assertTrue(game.state.entities[spawned_id]["visible"])
        self.assertTrue(game.state.entities[spawned_id]["available"])
        self.assertIn(spawned_id, game.state.script["entities"])

        # Turn 2 — open the discovered compartment
        open_action = {
            "intent_family": "open",
            "type": "open",
            "target": str(game.state.entities[spawned_id].get("name", "暗格")),
            "target_id": spawned_id,
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "打开暗格",
            "method": "打开暗格",
        }
        game.rules = RuleEngine(random.Random(0))

        with patch("diceflow.app.game.parse_intent", return_value=open_action):
            record2 = game.run_turn("打开暗格")

        self.assertEqual(record2.action["intent_family"], "open")
        self.assertNotEqual(record2.validation["reason"], "dynamic_adjudication")
        self.assertFalse(record2.check.get("dynamic", False))
        self.assertEqual(resolve_action_spec(open_action, game.state)["scope"], "entity")
        self.assertEqual(record2.check["result"], "success")
        self.assertTrue(game.state.entities[spawned_id].get("opened"))


    def test_discover_override_overrules_llm_improvised(self) -> None:
        """LLM returning improvised for a search action should be overridden to discover."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.adjudicator = DynamicAdjudicator(random.Random(0))

        # Mock LLM that would misclassify search as improvised
        mock_llm = MagicMock()
        mock_llm.evaluate_dynamic_action.return_value = {
            "plausibility": "reasonable",
            "difficulty": "medium",
            "risk": "medium",
            "intent_kind": "improvised",
        }
        game.llm = mock_llm

        action = {
            "intent_family": "unknown",
            "type": "unknown",
            "target": "",
            "target_id": "",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "我搜索墙上有没有暗格",
            "method": "我搜索墙上有没有暗格",
        }

        with patch("diceflow.app.game.parse_intent", return_value=action):
            record = game.run_turn("我搜索墙上有没有暗格")

        self.assertEqual(record.check["assessment"]["intent_kind"], "discover")
        self.assertIn("spawn_entities", record.state_changes)

    def test_discover_no_empty_target_id_in_entities(self) -> None:
        """Discover with no target should not produce entities['']."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.adjudicator = DynamicAdjudicator(random.Random(0))

        action = {
            "intent_family": "unknown",
            "type": "unknown",
            "target": "",
            "target_id": "",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "搜索周围有没有线索",
            "method": "搜索周围有没有线索",
        }

        with patch("diceflow.app.game.parse_intent", return_value=action):
            record = game.run_turn("搜索周围有没有线索")

        state_changes = record.state_changes
        entities_key = state_changes.get("entities", {})
        self.assertNotIn("", entities_key,
                         "Should not write to entities[''] when target_id is empty")

    def test_discover_failure_no_hp_damage(self) -> None:
        """Discover failure should not deduct HP or use combat fail template directly."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        adj = DynamicAdjudicator(random.Random(0))

        action: dict[str, Any] = {
            "intent_family": "unknown",
            "type": "unknown",
            "target": "",
            "target_id": "",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "搜索周围有没有线索",
            "method": "搜索周围有没有线索",
        }

        for result, expected_substring in [
            ("fail", "没有找到明确线索"),
            ("critical_fail", "弄出了声响"),
        ]:
            check: CheckResult = {
                "dc": 13,
                "roll": 5,
                "result": result,
                "dynamic": True,
                "assessment": {
                    "intent_kind": "discover",
                    "risk": "low",
                    "difficulty": "medium",
                    "plausibility": "reasonable",
                },
            }
            changes = adj.update_state(action, check, game.state)
            self.assertNotIn(
                "player", changes,
                f"Discover {result} should not deduct HP",
            )
            events = " ".join(changes.get("events", []))
            self.assertIn(
                expected_substring, events,
                f"Discover {result} events should contain '{expected_substring}', got: {events}",
            )
            self.assertFalse(
                any(word in events for word in ("反制", "识破")),
                f"Discover {result} should not use combat fail template, got: {events}",
            )

    def test_discover_success_spawns_dynamic_entity_from_keywords(self) -> None:
        """Different discover keywords should all spawn a dynamic entity on success."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.adjudicator = DynamicAdjudicator(random.Random(0))

        for input_text in ("找找周围有没有线索", "查看可疑痕迹", "检查脚印"):
            record = game.run_turn(input_text)
            if record.check["result"] in ("success", "critical_success"):
                self.assertIn(
                    "spawn_entities", record.state_changes,
                    f"'{input_text}' success should spawn entities",
                )

    def test_targetless_dynamic_failure_without_hostiles_does_not_revive_guard(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})
        self.assertFalse(game.state.entities["guard_1"]["alive"])
        self.assertEqual(game.state.get_hostile_entities(), {})

        action: dict[str, Any] = {
            "intent_family": "move",
            "type": "move",
            "target": "内部",
            "target_id": "",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "进入内部",
            "method": "进入内部",
        }
        check: CheckResult = {
            "dc": 17,
            "roll": 12,
            "result": "fail",
            "dynamic": True,
            "assessment": {
                "intent_kind": "improvised",
                "risk": "high",
                "difficulty": "hard",
                "plausibility": "reasonable",
            },
        }

        changes = DynamicAdjudicator().update_state(action, check, game.state)

        self.assertNotIn("player", changes)
        self.assertEqual(changes.get("entities", {}), {})
        self.assertFalse(game.state.entities["guard_1"]["alive"])
        events = " ".join(changes.get("events", []))
        self.assertNotIn("识破", events)
        self.assertNotIn("反制", events)

    def test_compact_state_excludes_dead_unavailable_guard_from_narrator_context(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})

        compact = _compact_state(game.state)

        self.assertNotIn("guard_1", compact["entities"])
        self.assertNotIn("守卫", compact["scene"]["visible_entities"])


    def test_transition_through_open_door_does_not_mark_entity_distracted(self) -> None:
        """Moving through an open door should get intent_kind=transition and not mark entities."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        adj = DynamicAdjudicator(random.Random(0))

        # Set up: door is already open
        game.state.flags["door_open"] = True
        game.state.entities["left_door"]["opened"] = True
        game.state.entities["left_door"]["locked"] = False

        action: dict[str, Any] = {
            "intent_family": "move",
            "type": "move",
            "target": "左门",
            "target_id": "left_door",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "进入左门后的通道",
            "method": "进入左门后的通道",
        }

        assessment = adj.assess(action, game.state)
        self.assertEqual(assessment["intent_kind"], "transition")

        check = adj.resolve(assessment)
        changes = adj.update_state(action, check, game.state)

        entities = changes.get("entities", {})
        self.assertEqual(entities, {}, "Transition should not mark any entity as distracted")
        self.assertTrue(changes.get("flags", {}).get("scene_transition", False))

    def test_transition_failure_no_hp_damage(self) -> None:
        """Transition failure should not deduct HP."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        adj = DynamicAdjudicator(random.Random(0))

        game.state.flags["door_open"] = True
        game.state.entities["left_door"]["opened"] = True

        action: dict[str, Any] = {
            "intent_family": "move",
            "type": "move",
            "target": "左门",
            "target_id": "left_door",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "进入左门后的通道",
            "method": "进入左门后的通道",
        }

        for result, expected_substring in [
            ("fail", "没有找到明确的通路"),
            ("critical_fail", "发出了声响"),
        ]:
            check: CheckResult = {
                "dc": 9,
                "roll": 3 if result == "fail" else 1,
                "result": result,
                "dynamic": True,
                "assessment": {
                    "intent_kind": "transition",
                    "risk": "low",
                    "difficulty": "easy",
                    "plausibility": "reasonable",
                },
            }
            changes = adj.update_state(action, check, game.state)
            self.assertNotIn(
                "player", changes,
                f"Transition {result} should not deduct HP",
            )
            events = " ".join(changes.get("events", []))
            self.assertIn(
                expected_substring, events,
                f"Transition {result} events should contain '{expected_substring}', got: {events}",
            )


if __name__ == "__main__":
    unittest.main()
