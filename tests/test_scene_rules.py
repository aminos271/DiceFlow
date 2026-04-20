import unittest

from diceflow.game import Game
from diceflow.validator import validate


class SceneRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(use_llm=False)

    def test_guard_alive_blocks_opening_left_door(self) -> None:
        action = {"type": "open", "target": "\u5de6\u95e8", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("\u5b88\u536b", result["reason"])

    def test_weakened_door_reduces_open_dc_by_three(self) -> None:
        self.game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})
        action = {"type": "open", "target": "\u5de6\u95e8", "method": "", "tool": ""}
        self.assertTrue(validate(action, self.game.state)["valid"])

        normal_dc = self.game.rules._dc_for(action, self.game.state)
        self.game.state.apply_changes({"entities": {"left_door": {"weakened": True}}})
        weakened_dc = self.game.rules._dc_for(action, self.game.state)

        self.assertEqual(weakened_dc, normal_dc - 3)

    def test_non_hostile_guard_reduces_attack_dc_by_two(self) -> None:
        action = {"type": "attack", "target": "\u5b88\u536b", "method": "", "tool": ""}
        self.assertTrue(validate(action, self.game.state)["valid"])

        hostile_dc = self.game.rules._dc_for(action, self.game.state)
        self.game.state.apply_changes({"entities": {"guard_1": {"hostile": False}}})
        non_hostile_dc = self.game.rules._dc_for(action, self.game.state)

        self.assertEqual(non_hostile_dc, hostile_dc - 2)


if __name__ == "__main__":
    unittest.main()

