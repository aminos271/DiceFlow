import unittest

from diceflow.core.derivation import derive_state_changes
from diceflow.core.models import StateChanges
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
        self.state.script["implied_entity_templates"] = {
            "shield": {
                "id_template": "$source_id_shield",
                "entity": {
                    "name": "盾牌",
                    "aliases": ["shield", "盾牌", "圆盾", "$source_name的盾牌"],
                    "type": "pickup",
                    "tags": ["equipment", "shield", "盾牌", "implied", "derived"],
                    "lifecycle": {
                        "category": "derived",
                        "cleanup": {"policy": "never"},
                    },
                },
            },
        }
        self.state.script["implied_entity_rules"] = []

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
        self.assertEqual(result["_normalized_action"]["target_id"], "skeleton_1_shield")
        self.assertIn("skeleton_1_shield", self.state.entities)
        shield = self.state.entities["skeleton_1_shield"]
        self.assertEqual(shield["lifecycle"]["origin"]["kind"], "derived")
        self.assertEqual(shield["lifecycle"]["origin"]["source_entity_id"], "skeleton_1")

    def test_missing_implied_template_does_not_spawn_empty_entity(self) -> None:
        self.state.script["implied_entity_templates"] = {}
        self.state.entities["skeleton_1"]["implied_equipment"] = ["shield"]
        action = {"type": "take", "target": "shield", "method": "", "tool": ""}

        result = validate(action, self.state)

        self.assertFalse(result["valid"])
        self.assertNotIn("skeleton_1_shield", self.state.entities)

    def test_string_implied_equipment_resolves_like_list(self) -> None:
        self.state.entities["skeleton_1"]["implied_equipment"] = "shield"
        action = {"type": "take", "target": "shield", "method": "", "tool": ""}

        result = validate(action, self.state)

        self.assertTrue(result["valid"])
        self.assertEqual(result["_normalized_action"]["target_id"], "skeleton_1_shield")

    def test_chinese_possessive_target_resolves_script_implied_equipment(self) -> None:
        state = GameState(load_script("tomb_entrance"))
        state.script["implied_entity_templates"] = {
            "shield": {
                "id_template": "$source_id_shield",
                "entity": {
                    "name": "盾牌",
                    "aliases": ["shield", "盾牌", "圆盾", "$source_name的盾牌"],
                    "type": "pickup",
                    "tags": ["equipment", "shield", "盾牌", "implied", "derived"],
                    "lifecycle": {
                        "category": "derived",
                        "cleanup": {"policy": "never"},
                    },
                },
            },
        }
        state.script["implied_entity_rules"] = []
        state.entities["guard_1"]["hp"] = 0
        state.entities["guard_1"]["alive"] = False
        state.entities["guard_1"]["implied_equipment"] = ["shield"]
        action = {"type": "take", "target": "他的盾牌", "method": "缴获他的盾牌", "tool": ""}

        result = validate(action, state)

        self.assertTrue(result["valid"])
        self.assertEqual(result["_normalized_action"]["target_id"], "guard_1_shield")
        self.assertIn("guard_1_shield", state.entities)
        shield = state.entities["guard_1_shield"]
        self.assertEqual(shield["name"], "盾牌")
        self.assertIn("守卫的盾牌", shield["aliases"])
        self.assertEqual(shield["lifecycle"]["origin"]["source_entity_id"], "guard_1")


    def test_spawn_with_implied_equipment_generates_items(self) -> None:
        """Eager generation: spawning an entity with implied_equipment
        also generates the implied items in the same state change."""
        action = {"type": "attack", "target_id": "chest_1"}
        explicit_changes: StateChanges = {
            "entities": {"chest_1": {"destroyed": True, "available": False}},
            "spawn_entities": {
                "new_guard": {
                    "name": "援军守卫",
                    "type": "human",
                    "tags": ["enemy", "hostile"],
                    "implied_equipment": ["shield"],
                },
            },
        }

        changes = derive_state_changes(action, {"result": "success"}, explicit_changes, self.state)

        self.assertIn("new_guard", changes["spawn_entities"])
        self.assertIn("new_guard_shield", changes["spawn_entities"])
        shield = changes["spawn_entities"]["new_guard_shield"]
        self.assertEqual(shield["name"], "盾牌")
        self.assertEqual(shield["_origin_kind"], "derived")
        self.assertEqual(shield["_source_entity_id"], "new_guard")
        self.assertEqual(shield["_rule_id"], "implied:shield")

    def test_spawn_implied_entity_skips_if_already_present(self) -> None:
        """If the implied entity already exists in spawn_entities,
        do not generate a duplicate."""
        action = {"type": "attack", "target_id": "chest_1"}
        explicit_changes: StateChanges = {
            "entities": {"chest_1": {"destroyed": True, "available": False}},
            "spawn_entities": {
                "new_guard": {
                    "name": "援军守卫",
                    "type": "human",
                    "implied_equipment": ["shield"],
                },
                "new_guard_shield": {"name": "custom shield", "tags": ["custom"]},
            },
        }

        changes = derive_state_changes(action, {"result": "success"}, explicit_changes, self.state)

        self.assertIn("new_guard_shield", changes["spawn_entities"])
        shield = changes["spawn_entities"]["new_guard_shield"]
        self.assertEqual(shield["name"], "custom shield")

    def test_spawn_implied_entity_template_placeholders(self) -> None:
        """$source_name in implied entity templates should be replaced
        with the spawning entity's name."""
        action = {"type": "attack", "target_id": "chest_1"}
        explicit_changes: StateChanges = {
            "entities": {"chest_1": {"destroyed": True, "available": False}},
            "spawn_entities": {
                "guard_reinforce": {
                    "name": "守卫援军",
                    "type": "human",
                    "implied_equipment": ["shield"],
                },
            },
        }

        changes = derive_state_changes(action, {"result": "success"}, explicit_changes, self.state)

        self.assertIn("guard_reinforce_shield", changes["spawn_entities"])
        shield = changes["spawn_entities"]["guard_reinforce_shield"]
        self.assertIn("守卫援军的盾牌", shield["aliases"])


if __name__ == "__main__":
    unittest.main()
