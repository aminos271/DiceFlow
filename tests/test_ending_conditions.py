import unittest

from diceflow.game import Game


class EndingConditionsTest(unittest.TestCase):
    def test_victory_when_door_open_and_guard_dead(self) -> None:
        game = Game(use_llm=False)

        game.state.apply_changes(
            {
                "entities": {"guard_1": {"hp_delta": -6}},
                "flags": {"door_open": True},
            }
        )

        self.assertTrue(game.state.flags["game_over"])
        self.assertEqual(game.state.flags["ending"], "victory")

    def test_death_when_player_hp_reaches_zero(self) -> None:
        game = Game(use_llm=False)

        game.state.apply_changes({"player": {"hp_delta": -10}})

        self.assertTrue(game.state.flags["game_over"])
        self.assertEqual(game.state.flags["ending"], "death")

    def test_timeout_when_turn_id_reaches_twenty(self) -> None:
        game = Game(use_llm=False)
        game.state.turn_id = 20

        game.state.apply_changes({"events": ["时间耗尽。"]})

        self.assertTrue(game.state.flags["game_over"])
        self.assertEqual(game.state.flags["ending"], "timeout")


if __name__ == "__main__":
    unittest.main()

