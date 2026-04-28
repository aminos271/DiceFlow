import unittest

from diceflow.app.game import Game
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class ValidatorDataDrivenTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("tomb_entrance"), use_llm=False)

    def test_guard_allows_attack(self) -> None:
        action = {"type": "attack", "target": "守卫", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertTrue(result["valid"])
        self.assertEqual(result["_normalized_action"]["target_id"], "guard_1")

    def test_left_door_does_not_allow_attack(self) -> None:
        action = {"type": "attack", "target": "左门", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("attack", result["reason"])

    def test_burn_requires_torch(self) -> None:
        self.game.state.apply_changes({"player": {"inventory_remove": ["火把"]}})
        action = {"type": "burn", "target": "左门", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("火把", result["reason"])

    def test_unknown_target_is_invalid(self) -> None:
        action = {"type": "attack", "target": "石像", "method": "", "tool": ""}

        result = validate(action, self.game.state)

        self.assertFalse(result["valid"])
        self.assertIn("目标", result["reason"])

    def test_dungeon_corridor_allows_scene_move(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        action = {"type": "move", "target": "铁门", "method": "往铁门移动", "tool": ""}

        result = validate(action, game.state)

        self.assertTrue(result["valid"])

    def test_dungeon_corridor_allows_unknown_fallback(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        action = {"type": "unknown", "target": "", "method": "", "tool": ""}

        result = validate(action, game.state)

        self.assertTrue(result["valid"])

    def test_dungeon_corridor_use_key_on_iron_door(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        game.state.apply_changes({"player": {"inventory_add": ["铁钥匙"]}})
        action = {
            "intent_family": "use",
            "target": "铁门",
            "tool": "铁钥匙",
            "approach_tags": ["careful"],
            "method_text": "低调地把铁钥匙插进锁孔",
        }

        result = validate(action, game.state)

        self.assertTrue(result["valid"])
        self.assertEqual(result["_normalized_action"]["target_id"], "iron_door")
        self.assertEqual(result["_normalized_action"]["tool_id"], "铁钥匙")

    def test_use_requires_matching_tool_id(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        game.state.apply_changes({"player": {"inventory_add": ["铁钥匙", "短剑"]}})
        action = {
            "intent_family": "use",
            "target": "铁门",
            "tool": "短剑",
            "method_text": "用短剑撬铁门",
        }

        result = validate(action, game.state)

        self.assertFalse(result["valid"])
        self.assertIn("铁钥匙", result["reason"])


if __name__ == "__main__":
    unittest.main()
