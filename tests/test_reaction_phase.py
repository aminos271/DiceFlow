import unittest

from diceflow.app.game import Game
from diceflow.core.reaction import reaction_phase
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class ReactionPhaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("tomb_entrance"), use_llm=False)
        self.attack_guard = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        result = validate(self.attack_guard, self.game.state)
        self.assertTrue(result["valid"])
        self.attack_guard = result.get("_normalized_action", self.attack_guard)

    def test_hostile_target_reacts_after_successful_attack(self) -> None:
        action_changes = update_state(self.attack_guard, {"result": "success"}, self.game.state)
        self.game.state.apply_changes(action_changes)

        reaction_changes = reaction_phase(
            self.attack_guard,
            {"result": "success"},
            action_changes,
            self.game.state,
        )

        self.assertEqual(reaction_changes["player"]["hp_delta"], -2)
        self.assertIn("events", reaction_changes)

    def test_dead_target_does_not_react(self) -> None:
        action_changes = {"entities": {"guard_1": {"hp_delta": -6}}}
        self.game.state.apply_changes(action_changes)

        reaction_changes = reaction_phase(
            self.attack_guard,
            {"result": "success"},
            action_changes,
            self.game.state,
        )

        self.assertEqual(reaction_changes, {})


if __name__ == "__main__":
    unittest.main()
