import unittest

from diceflow.app.game import Game
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class ValidatorDataDrivenTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("tomb_entrance"), use_llm=False)

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

    def test_dungeon_corridor_allows_scene_move(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        action = {"type": "move", "target": "\u94c1\u95e8", "method": "\u5f80\u94c1\u95e8\u79fb\u52a8", "tool": ""}

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
            "target": "\u94c1\u95e8",
            "tool": "\u94c1\u94a5\u5319",
            "approach_tags": ["careful"],
            "method_text": "\u4f4e\u8c03\u5730\u628a\u94c1\u94a5\u5319\u63d2\u8fdb\u9501\u5b54",
        }

        result = validate(action, game.state)

        self.assertTrue(result["valid"])
        self.assertEqual(action["target_id"], "iron_door")
        self.assertEqual(action["tool_id"], "\u94c1\u94a5\u5319")

    def test_use_requires_matching_tool_id(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        game.state.apply_changes({"player": {"inventory_add": ["铁钥匙", "短剑"]}})
        action = {
            "intent_family": "use",
            "target": "\u94c1\u95e8",
            "tool": "\u77ed\u5251",
            "method_text": "\u7528\u77ed\u5251\u64ac\u94c1\u95e8",
        }

        result = validate(action, game.state)

        self.assertFalse(result["valid"])
        self.assertIn("\u94c1\u94a5\u5319", result["reason"])


if __name__ == "__main__":
    unittest.main()
