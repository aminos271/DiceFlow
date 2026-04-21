import unittest

from diceflow.app.game import Game
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class SceneRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("tomb_entrance"), use_llm=False)

    def test_guard_alive_blocks_opening_left_door(self) -> None:
        action = {"type": "open", "target": "左门", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("守卫", result["reason"])

    def test_weakened_door_reduces_open_dc_by_three(self) -> None:
        self.game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})
        action = {"type": "open", "target": "左门", "method": "", "tool": ""}
        self.assertTrue(validate(action, self.game.state)["valid"])

        normal_dc = self.game.rules._dc_for(action, self.game.state)
        self.game.state.apply_changes({"entities": {"left_door": {"weakened": True}}})
        weakened_dc = self.game.rules._dc_for(action, self.game.state)

        self.assertEqual(weakened_dc, normal_dc - 3)

    def test_non_hostile_guard_reduces_attack_dc_by_two(self) -> None:
        action = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        self.assertTrue(validate(action, self.game.state)["valid"])

        hostile_dc = self.game.rules._dc_for(action, self.game.state)
        self.game.state.apply_changes({"entities": {"guard_1": {"hostile": False}}})
        non_hostile_dc = self.game.rules._dc_for(action, self.game.state)

        self.assertEqual(non_hostile_dc, hostile_dc - 2)

    def test_approach_tags_modify_dc(self) -> None:
        self.game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})
        normal_action = {"type": "open", "target": "左门", "method": "", "tool": ""}
        careful_action = {
            "type": "open",
            "target": "左门",
            "method": "小心开门",
            "tool": "",
            "approach_tags": ["careful"],
        }
        quick_action = {
            "type": "open",
            "target": "左门",
            "method": "立刻开门",
            "tool": "",
            "approach_tags": ["quick"],
        }
        self.assertTrue(validate(normal_action, self.game.state)["valid"])
        self.assertTrue(validate(careful_action, self.game.state)["valid"])
        self.assertTrue(validate(quick_action, self.game.state)["valid"])

        normal_dc = self.game.rules._dc_for(normal_action, self.game.state)

        self.assertEqual(self.game.rules._dc_for(careful_action, self.game.state), normal_dc - 1)
        self.assertEqual(self.game.rules._dc_for(quick_action, self.game.state), normal_dc + 1)


if __name__ == "__main__":
    unittest.main()
