import random
import unittest
from unittest.mock import patch

from diceflow.app.game import Game
from diceflow.core.adjudicator import DynamicAdjudicator
from diceflow.scripting.loader import load_script


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


if __name__ == "__main__":
    unittest.main()
