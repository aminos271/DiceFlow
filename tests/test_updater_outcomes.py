import unittest

from diceflow.app.game import Game
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class UpdaterOutcomesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("tomb_entrance"), use_llm=False)
        self.attack_guard = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        result = validate(self.attack_guard, self.game.state)
        self.assertTrue(result["valid"])
        self.attack_guard = result.get("_normalized_action", self.attack_guard)

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

    def test_critical_success_falls_back_to_success_outcome(self) -> None:
        game = Game(script=load_script("border_town_campaign"), use_llm=False)
        action = {"type": "inspect", "target": "酒馆老板", "method": "", "tool": ""}
        result = validate(action, game.state)
        self.assertTrue(result["valid"])
        action = result.get("_normalized_action", action)

        changes = update_state(action, {"result": "critical_success"}, game.state)

        self.assertNotIn("player", changes)
        self.assertIn("events", changes)
        self.assertIn("老板", changes["events"][0])


if __name__ == "__main__":
    unittest.main()
