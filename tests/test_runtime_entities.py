import unittest

from diceflow.app.game import Game
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script
from diceflow.scripting.resolver import resolve_action_spec


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
        action_spec = resolve_action_spec(smash, self.game.state)
        self.assertEqual(action_spec["scope"], "generic_rule")

        smash_changes = update_state(smash, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(smash_changes)

        self.assertTrue(self.game.state.entities["chest_1"]["destroyed"])
        self.assertFalse(self.game.state.entities["chest_1"]["available"])
        self.assertIn("chest_1_debris", self.game.state.entities)
        self.assertTrue(self.game.state.entities["chest_1_debris"]["available"])
        self.assertTrue(self.game.state.entities["iron_key"]["visible"])

        take_revealed_key = {
            "type": "take",
            "target": "铁钥匙",
            "method": "拿起铁钥匙",
            "tool": "",
        }
        self.assertTrue(validate(take_revealed_key, self.game.state)["valid"])

        take_changes = update_state(take_revealed_key, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(take_changes)
        self.game.state.apply_changes(take_changes)

        self.assertEqual(self.game.state.player["inventory"].count("铁钥匙"), 1)
        self.assertTrue(self.game.state.entities["iron_key"]["looted"])

    def test_throw_chest_at_skeleton_uses_same_generic_rule(self) -> None:
        throw = {
            "type": "throw",
            "target": "骷髅",
            "tool": "木箱",
            "method": "投掷木箱砸骷髅",
        }
        self.assertTrue(validate(throw, self.game.state)["valid"])

        action_spec = resolve_action_spec(throw, self.game.state)

        self.assertEqual(action_spec["scope"], "generic_rule")
        self.assertEqual(action_spec["dc"], 10)


if __name__ == "__main__":
    unittest.main()
