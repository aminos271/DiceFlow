import unittest

from diceflow.core.derivation import derive_state_changes
from diceflow.core.state import GameState
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script


class DerivationTest(unittest.TestCase):
    def setUp(self) -> None:
        script = load_script("dungeon_corridor")
        self.state = GameState(script)
        self.state.script["derivation_rules"] = [
            {
                "id": "wood_breaks_into_debris",
                "when": {
                    "result": ["success", "critical_success"],
                    "target_tags": ["throwable"],
                    "target": {"destroyed": True},
                },
                "spawn": {
                    "id_template": "$target_id_debris_auto",
                    "entity": {
                        "name": "$target_name debris",
                        "type": "pickup",
                        "tags": ["debris", "derived"],
                        "lifecycle": {
                            "category": "temporary",
                            "cleanup": {"policy": "after_turns", "ttl_turns": 2},
                        },
                    },
                },
            }
        ]

    def test_destroyed_target_spawns_derived_entity(self) -> None:
        action = {"type": "attack", "target_id": "chest_1"}
        explicit_changes = {"entities": {"chest_1": {"destroyed": True, "available": False}}}

        changes = derive_state_changes(action, {"result": "success"}, explicit_changes, self.state)

        self.assertIn("chest_1_debris_auto", changes["spawn_entities"])
        debris = changes["spawn_entities"]["chest_1_debris_auto"]
        self.assertEqual(debris["_origin_kind"], "derived")
        self.assertEqual(debris["_source_entity_id"], "chest_1")
        self.assertEqual(debris["_rule_id"], "wood_breaks_into_debris")
        self.assertEqual(debris["lifecycle"]["category"], "temporary")

    def test_existing_spawn_is_not_duplicated(self) -> None:
        action = {"type": "attack", "target_id": "chest_1"}
        explicit_changes = {
            "entities": {"chest_1": {"destroyed": True, "available": False}},
            "spawn_entities": {"chest_1_debris_auto": {"name": "already present"}},
        }

        changes = derive_state_changes(action, {"result": "success"}, explicit_changes, self.state)

        self.assertEqual(changes["spawn_entities"]["chest_1_debris_auto"]["name"], "already present")

    def test_missing_target_can_be_resolved_from_implied_equipment(self) -> None:
        self.state.entities["skeleton_1"]["implied_equipment"] = ["shield"]
        action = {"type": "take", "target": "shield", "method": "", "tool": ""}

        result = validate(action, self.state)

        self.assertTrue(result["valid"])
        self.assertEqual(action["target_id"], "skeleton_1_shield")
        self.assertIn("skeleton_1_shield", self.state.entities)
        shield = self.state.entities["skeleton_1_shield"]
        self.assertEqual(shield["lifecycle"]["origin"]["kind"], "derived")
        self.assertEqual(shield["lifecycle"]["origin"]["source_entity_id"], "skeleton_1")


if __name__ == "__main__":
    unittest.main()
