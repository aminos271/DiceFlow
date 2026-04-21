import random
import unittest

from diceflow.app.game import Game
from diceflow.core.rules import RuleEngine
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class GameLoopTest(unittest.TestCase):
    def test_heuristic_loop_updates_state(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.rules = RuleEngine(random.Random(0))

        first = game.run_turn("攻击守卫")
        second = game.run_turn("攻击守卫")
        third = game.run_turn("检查左门")

        self.assertEqual(first.action["type"], "attack")
        self.assertEqual(first.action["target_id"], "guard_1")
        self.assertTrue(second.validation["valid"])
        self.assertTrue(third.state_changes["flags"]["found_exit"])
        self.assertLessEqual(game.state.entities["guard_1"]["hp"], 6)

    def test_state_authority_reaches_victory(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)

        game.state.apply_changes(
            {
                "entities": {
                    "guard_1": {"hp_delta": -6},
                    "left_door": {"locked": False},
                }
            }
        )
        game.state.apply_changes({"flags": {"door_open": True}})

        self.assertTrue(game.state.flags["game_over"])
        self.assertEqual(game.state.flags["ending"], "victory")

    def test_validator_uses_entity_allowed_actions(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)

        attack_door = {"type": "attack", "target": "左门", "method": "", "tool": ""}
        open_guard = {"type": "open", "target": "守卫", "method": "", "tool": ""}

        self.assertFalse(validate(attack_door, game.state)["valid"])
        self.assertFalse(validate(open_guard, game.state)["valid"])

    def test_game_accepts_loaded_script(self) -> None:
        script = load_script("tomb_entrance")
        game = Game(script=script, use_llm=False)

        self.assertEqual(game.state.scene["name"], "古墓入口")
        self.assertIn("guard_1", game.state.entities)

    def test_scene_rule_blocks_opening_door_while_guard_alive(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        action = {"type": "open", "target": "左门", "method": "", "tool": ""}

        result = validate(action, game.state)

        self.assertFalse(result["valid"])
        self.assertIn("守卫", result["reason"])

    def test_weakened_door_reduces_open_dc(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})
        action = {"type": "open", "target": "左门", "method": "", "tool": ""}
        self.assertTrue(validate(action, game.state)["valid"])

        normal_dc = game.rules._dc_for(action, game.state)
        game.state.apply_changes({"entities": {"left_door": {"weakened": True}}})
        weakened_dc = game.rules._dc_for(action, game.state)

        self.assertEqual(normal_dc, 14)
        self.assertEqual(weakened_dc, 11)

    def test_action_effects_come_from_entity_metadata(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        game.state.apply_changes({"entities": {"guard_1": {"hp_delta": -6}}})
        action = {"type": "open", "target": "左门", "method": "", "tool": ""}
        self.assertTrue(validate(action, game.state)["valid"])

        changes = update_state(action, {"result": "success", "dc": 14, "roll": 14}, game.state)

        self.assertTrue(changes["flags"]["door_open"])


if __name__ == "__main__":
    unittest.main()
