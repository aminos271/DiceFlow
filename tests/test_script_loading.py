import unittest

from diceflow.game import Game
from diceflow.script import get_action_spec, load_script, validate_script
from diceflow.validator import validate


class ScriptLoadingTest(unittest.TestCase):
    def test_load_tomb_entrance_script(self) -> None:
        script = load_script("tomb_entrance")

        self.assertEqual(script["id"], "tomb_entrance")
        self.assertIn("player", script)
        self.assertIn("scene", script)
        self.assertIn("entities", script)
        self.assertIn("flags", script)
        self.assertIn("scene_actions", script)
        self.assertIn("ending_conditions", script)

    def test_required_entity_action_fields_exist(self) -> None:
        script = load_script("tomb_entrance")

        for entity in script["entities"].values():
            self.assertIn("metadata", entity)
            self.assertIn("actions", entity["metadata"])
            for action in entity["metadata"]["actions"].values():
                self.assertIn("dc", action)
                self.assertIn("outcomes", action)

    def test_validate_script_accepts_builtin_script(self) -> None:
        script = load_script("tomb_entrance")

        validate_script(script)

    def test_validate_script_rejects_missing_top_level_field(self) -> None:
        script = load_script("tomb_entrance")
        del script["entities"]

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("missing top-level field: entities", str(context.exception))

    def test_validate_script_rejects_action_without_outcomes(self) -> None:
        script = load_script("tomb_entrance")
        del script["entities"]["guard_1"]["metadata"]["actions"]["attack"]["outcomes"]

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("outcomes is required", str(context.exception))

    def test_validate_script_rejects_misspelled_action_field(self) -> None:
        script = load_script("tomb_entrance")
        burn = script["entities"]["left_door"]["metadata"]["actions"]["burn"]
        burn["required_tool"] = burn.pop("required_tools")

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("unsupported action field: required_tool", str(context.exception))

    def test_validate_script_rejects_invalid_ending_key(self) -> None:
        script = load_script("tomb_entrance")
        script["ending_conditions"].append({"ending": "bad", "when": {"bad_key": True}})

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("unsupported key: bad_key", str(context.exception))

    def test_validate_script_rejects_target_placeholder_in_scene_action(self) -> None:
        script = load_script("tomb_entrance")
        script["scene_actions"]["wait"]["outcomes"]["success"] = {
            "entities": {"$target": {"weakened": True}},
        }

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("$target without an entity target", str(context.exception))

    def test_action_spec_prefers_target_entity_action(self) -> None:
        game = Game(use_llm=False)
        action = {"type": "inspect", "target": "\u5de6\u95e8", "method": "", "tool": ""}
        self.assertTrue(validate(action, game.state)["valid"])

        action_spec = get_action_spec(action, game.state)

        self.assertEqual(action_spec["dc"], 10)
        self.assertIn("flags", action_spec["outcomes"]["success"])

    def test_action_spec_uses_scene_action_without_target(self) -> None:
        game = Game(use_llm=False)
        action = {"type": "wait", "target": "", "method": "", "tool": ""}
        self.assertTrue(validate(action, game.state)["valid"])

        action_spec = get_action_spec(action, game.state)

        self.assertEqual(action_spec["dc"], 8)
        self.assertIn("events", action_spec["outcomes"]["success"])

    def test_loaded_scripts_are_deep_copied(self) -> None:
        first = load_script("tomb_entrance")
        second = load_script("tomb_entrance")
        first["entities"]["guard_1"]["hp"] = 1

        self.assertEqual(second["entities"]["guard_1"]["hp"], 6)


if __name__ == "__main__":
    unittest.main()
