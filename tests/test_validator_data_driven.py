import unittest

from diceflow.game import Game
from diceflow.validator import validate


class ValidatorDataDrivenTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(use_llm=False)

    def test_guard_allows_attack(self) -> None:
        action = {"type": "attack", "target": "\u5b88\u536b", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertTrue(result["valid"])
        self.assertEqual(action["target_id"], "guard_1")

    def test_left_door_does_not_allow_attack(self) -> None:
        action = {"type": "attack", "target": "\u5de6\u95e8", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("attack", result["reason"])

    def test_burn_requires_torch(self) -> None:
        self.game.state.apply_changes({"player": {"inventory_remove": ["火把"]}})
        action = {"type": "burn", "target": "\u5de6\u95e8", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("\u706b\u628a", result["reason"])

    def test_unknown_target_is_invalid(self) -> None:
        action = {"type": "attack", "target": "\u77f3\u50cf", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("\u76ee\u6807", result["reason"])


if __name__ == "__main__":
    unittest.main()

