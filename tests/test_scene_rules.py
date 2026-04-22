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

    def test_target_tags_modify_dc(self) -> None:
        # Add tags to guard_1 entity
        self.game.state.entities["guard_1"]["tags"] = ["enemy", "human"]
        # Add a dc_modifier that matches enemy tag
        modifier = {"when": {"target_tags": "enemy"}, "modifier": -5}
        # Ensure we don't mutate the original script dict
        script = self.game.state.script
        if "dc_modifiers" not in script:
            script["dc_modifiers"] = []
        script["dc_modifiers"].append(modifier)

        action = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        self.assertTrue(validate(action, self.game.state)["valid"])

        dc_with_tag = self.game.rules._dc_for(action, self.game.state)
        # Remove modifier to compute baseline
        script["dc_modifiers"].pop()
        # Add modifier with non-matching tag
        script["dc_modifiers"].append({"when": {"target_tags": "inanimate"}, "modifier": -5})
        dc_non_match = self.game.rules._dc_for(action, self.game.state)
        self.assertEqual(dc_non_match, 12)
        # Restore modifier with matching tag
        script["dc_modifiers"].pop()
        script["dc_modifiers"].append(modifier)
        dc_with_tag_again = self.game.rules._dc_for(action, self.game.state)
        self.assertEqual(dc_with_tag_again, dc_non_match - 5)

    def test_any_target_tags_modify_dc(self) -> None:
        self.game.state.entities["guard_1"]["tags"] = ["enemy", "human"]
        script = self.game.state.script
        if "dc_modifiers" not in script:
            script["dc_modifiers"] = []
        # Add modifier that matches any of the tags
        script["dc_modifiers"].append({"when": {"any_target_tags": ["enemy", "monster"]}, "modifier": -3})

        action = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        dc_with_tag = self.game.rules._dc_for(action, self.game.state)
        # Remove modifier
        script["dc_modifiers"].pop()
        dc_without_tag = self.game.rules._dc_for(action, self.game.state)
        self.assertEqual(dc_with_tag, dc_without_tag - 3)

    def test_tool_tags_modify_dc(self) -> None:
        # Add a tool entity (e.g., a magic sword) with tags
        self.game.state.entities["magic_sword"] = {
            "name": "魔法剑",
            "aliases": ["魔法剑", "剑"],
            "tags": ["magic", "weapon"],
            "metadata": {"allowed_actions": [], "actions": {}},
        }
        # Add tags to guard_1
        self.game.state.entities["guard_1"]["tags"] = ["enemy"]
        # Add dc_modifier that matches tool tags
        script = self.game.state.script
        if "dc_modifiers" not in script:
            script["dc_modifiers"] = []
        script["dc_modifiers"].append({"when": {"tool_tags": "magic"}, "modifier": -2})

        action_with_tool = {"type": "attack", "target": "守卫", "method": "", "tool": "魔法剑"}
        action_without_tool = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        dc_with_tool = self.game.rules._dc_for(action_with_tool, self.game.state)
        dc_without_tool = self.game.rules._dc_for(action_without_tool, self.game.state)
        self.assertEqual(dc_with_tool, dc_without_tool - 2)


if __name__ == "__main__":
    unittest.main()
