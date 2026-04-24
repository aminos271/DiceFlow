import unittest

from diceflow.app.game import Game
from diceflow.scripting.loader import load_script


class RuntimeScriptPatchTest(unittest.TestCase):
    def test_add_entity_patch_updates_script_and_state(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        patch = {
            "id": "test_add_entity",
            "source": "test",
            "turn_id": game.state.turn_id,
            "ops": [
                {
                    "op": "add_entity",
                    "id": "runtime_cache",
                    "entity": {
                        "name": "runtime cache",
                        "type": "container",
                        "tags": ["container", "dynamic"],
                    },
                }
            ],
        }

        game.state.apply_script_patch(patch)

        self.assertEqual(game.state.script_patches[0]["id"], "test_add_entity")
        self.assertIn("runtime_cache", game.state.script["entities"])
        self.assertIn("runtime_cache", game.state.entities)
        self.assertIn("open", game.state.entities["runtime_cache"]["metadata"]["allowed_actions"])

    def test_add_entity_patch_cannot_overwrite_existing_entity_id(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        patch = {
            "id": "test_overwrite_entity",
            "source": "test",
            "turn_id": game.state.turn_id,
            "ops": [
                {
                    "op": "add_entity",
                    "id": "guard_1",
                    "entity": {
                        "name": "replacement guard",
                        "type": "container",
                        "tags": ["dynamic"],
                    },
                }
            ],
        }

        with self.assertRaises(ValueError):
            game.state.apply_script_patch(patch)

        self.assertEqual(game.state.script_patches, [])
        self.assertNotEqual(game.state.entities["guard_1"]["name"], "replacement guard")


if __name__ == "__main__":
    unittest.main()
