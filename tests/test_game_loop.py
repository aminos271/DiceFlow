import random
import unittest

from diceflow.game import Game
from diceflow.rules import RuleEngine


class GameLoopTest(unittest.TestCase):
    def test_heuristic_loop_updates_state(self) -> None:
        game = Game(use_llm=False)
        game.rules = RuleEngine(random.Random(0))

        first = game.run_turn("\u653b\u51fb\u5b88\u536b")
        second = game.run_turn("\u653b\u51fb\u5b88\u536b")
        third = game.run_turn("\u68c0\u67e5\u5de6\u95e8")

        self.assertEqual(first.action["type"], "attack")
        self.assertEqual(first.action["target_id"], "guard_1")
        self.assertTrue(second.validation["valid"])
        self.assertTrue(third.state_changes["flags"]["found_exit"])
        self.assertLessEqual(game.state.entities["guard_1"]["hp"], 6)

    def test_state_authority_reaches_victory(self) -> None:
        game = Game(use_llm=False)

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


if __name__ == "__main__":
    unittest.main()

