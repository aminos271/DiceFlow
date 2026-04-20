import unittest

from diceflow.script import load_script


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


if __name__ == "__main__":
    unittest.main()

