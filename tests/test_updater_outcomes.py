import unittest

from diceflow.game import Game
from diceflow.updater import update_state
from diceflow.validator import validate


class UpdaterOutcomesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(use_llm=False)
        self.attack_guard = {"type": "attack", "target": "\u5b88\u536b", "method": "", "tool": ""}
        self.assertTrue(validate(self.attack_guard, self.game.state)["valid"])

    def test_success_maps_to_configured_changes(self) -> None:
        changes = update_state(self.attack_guard, {"result": "success"}, self.game.state)

        self.assertEqual(changes["entities"]["guard_1"]["hp_delta"], -3)
        self.assertIn("events", changes)

    def test_fail_maps_to_configured_changes(self) -> None:
        changes = update_state(self.attack_guard, {"result": "fail"}, self.game.state)

        self.assertEqual(changes["player"]["hp_delta"], -1)
        self.assertIn("events", changes)

    def test_critical_success_maps_to_configured_changes(self) -> None:
        changes = update_state(self.attack_guard, {"result": "critical_success"}, self.game.state)

        self.assertEqual(changes["entities"]["guard_1"]["hp_delta"], -5)

    def test_critical_fail_maps_to_configured_changes(self) -> None:
        changes = update_state(self.attack_guard, {"result": "critical_fail"}, self.game.state)

        self.assertEqual(changes["player"]["hp_delta"], -2)

    def test_target_placeholder_is_replaced(self) -> None:
        changes = update_state(self.attack_guard, {"result": "success"}, self.game.state)

        self.assertIn("guard_1", changes["entities"])
        self.assertNotIn("$target", changes["entities"])


if __name__ == "__main__":
    unittest.main()

