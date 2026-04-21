import unittest

from diceflow.app.game import Game
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class RuntimeEntitiesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("dungeon_corridor"), use_llm=False)

    def test_open_chest_reveals_real_key_then_take_moves_it_to_inventory(self) -> None:
        open_chest = {"type": "open", "target": "木箱", "method": "", "tool": ""}
        self.assertTrue(validate(open_chest, self.game.state)["valid"])

        open_changes = update_state(open_chest, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(open_changes)

        self.assertTrue(self.game.state.entities["chest_1"]["opened"])
        self.assertTrue(self.game.state.entities["iron_key"]["visible"])
        self.assertTrue(self.game.state.entities["iron_key"]["available"])
        self.assertNotIn("铁钥匙", self.game.state.player["inventory"])

        reopen_chest = {"type": "open", "target": "木箱", "method": "", "tool": ""}
        reopen_result = validate(reopen_chest, self.game.state)

        self.assertFalse(reopen_result["valid"])
        self.assertIn("已经打开", reopen_result["reason"])

        take_key = {"type": "take", "target": "铁钥匙", "method": "", "tool": ""}
        self.assertTrue(validate(take_key, self.game.state)["valid"])

        take_changes = update_state(take_key, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(take_changes)
        self.game.state.apply_changes(take_changes)

        self.assertEqual(self.game.state.player["inventory"].count("铁钥匙"), 1)
        self.assertFalse(self.game.state.entities["iron_key"]["visible"])
        self.assertFalse(self.game.state.entities["iron_key"]["available"])
        self.assertTrue(self.game.state.entities["iron_key"]["looted"])

        take_again = {"type": "take", "target": "铁钥匙", "method": "", "tool": ""}
        take_again_result = validate(take_again, self.game.state)

        self.assertFalse(take_again_result["valid"])

    def test_smash_skeleton_with_chest_spawns_debris_and_key_can_be_taken(self) -> None:
        smash = {
            "type": "use",
            "target": "骷髅",
            "tool": "木箱",
            "method": "用木箱砸骷髅",
        }
        self.assertTrue(validate(smash, self.game.state)["valid"])

        smash_changes = update_state(smash, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(smash_changes)

        self.assertTrue(self.game.state.entities["chest_1"]["destroyed"])
        self.assertFalse(self.game.state.entities["chest_1"]["available"])
        self.assertIn("chest_debris_1", self.game.state.entities)
        self.assertTrue(self.game.state.entities["chest_debris_1"]["available"])
        self.assertTrue(self.game.state.entities["iron_key"]["visible"])

        take_from_debris = {
            "type": "take",
            "target": "残片",
            "method": "从残片中翻找",
            "tool": "",
        }
        self.assertTrue(validate(take_from_debris, self.game.state)["valid"])

        take_changes = update_state(take_from_debris, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(take_changes)
        self.game.state.apply_changes(take_changes)

        self.assertEqual(self.game.state.player["inventory"].count("铁钥匙"), 1)
        self.assertTrue(self.game.state.entities["chest_debris_1"]["looted"])


if __name__ == "__main__":
    unittest.main()
