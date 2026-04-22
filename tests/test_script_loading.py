import unittest

from diceflow.app.game import Game
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script
from diceflow.scripting.resolver import get_action_spec, resolve_action_spec
from diceflow.scripting.validation import validate_script


class ScriptLoadingTest(unittest.TestCase):
    def test_load_tomb_entrance_script(self) -> None:
        script = load_script("tomb_entrance")

        self.assertEqual(script["schema_version"], 1)
        self.assertEqual(script["id"], "tomb_entrance")
        self.assertIn("player", script)
        self.assertIn("scene", script)
        self.assertIn("entities", script)
        self.assertIn("flags", script)
        self.assertIn("scene_actions", script)
        self.assertIn("ending_conditions", script)

    def test_load_dungeon_corridor_script(self) -> None:
        script = load_script("dungeon_corridor")

        self.assertEqual(script["id"], "dungeon_corridor")
        self.assertIn("skeleton_1", script["entities"])
        self.assertIn("generic_rules", script)
        self.assertIn("flee", script["scene_actions"])
        self.assertNotIn("flee", script["entities"]["skeleton_1"]["metadata"]["allowed_actions"])

    def test_dungeon_corridor_uses_generic_rules_for_common_combat(self) -> None:
        script = load_script("dungeon_corridor")
        skeleton_actions = script["entities"]["skeleton_1"]["metadata"]["actions"]
        rule_ids = {rule["id"] for rule in script["generic_rules"]}

        self.assertNotIn("attack", skeleton_actions)
        self.assertNotIn("use", skeleton_actions)
        self.assertIn("attack_enemy", rule_ids)
        self.assertIn("heavy_throwable_hits_fragile_enemy", rule_ids)

    def test_dungeon_corridor_entities_are_archetype_materialized(self) -> None:
        script = load_script("dungeon_corridor")

        chest = script["entities"]["chest_1"]
        key = script["entities"]["iron_key"]
        door = script["entities"]["iron_door"]

        self.assertEqual(chest["type"], "container")
        self.assertIn("open", chest["metadata"]["actions"])
        self.assertEqual(chest["metadata"]["actions"]["open"]["outcomes"]["success"]["reveal_entities"], ["iron_key"])
        self.assertEqual(key["type"], "pickup")
        self.assertIn("take", key["metadata"]["actions"])
        self.assertEqual(key["metadata"]["actions"]["take"]["outcomes"]["success"]["flags"], {"has_key": True})
        self.assertEqual(door["type"], "door")
        self.assertEqual(door["metadata"]["actions"]["open"]["required_tools"], ["铁钥匙"])

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

    def test_validate_script_rejects_unknown_top_level_field(self) -> None:
        script = load_script("tomb_entrance")
        script["unexpected"] = True

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("unsupported top-level field: unexpected", str(context.exception))

    def test_validate_script_rejects_wrong_schema_version(self) -> None:
        script = load_script("tomb_entrance")
        script["schema_version"] = 2

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("schema_version must be 1", str(context.exception))

    def test_validate_script_accepts_tag_only_entity(self) -> None:
        script = load_script("tomb_entrance")
        script["entities"]["loose_stone"] = {
            "name": "松动石块",
            "aliases": ["石块"],
            "tags": ["movable", "heavy", "throwable"],
        }

        validate_script(script)

    def test_validate_script_rejects_action_without_outcomes(self) -> None:
        script = load_script("tomb_entrance")
        del script["entities"]["guard_1"]["metadata"]["actions"]["attack"]["outcomes"]

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("outcomes is required", str(context.exception))

    def test_validate_script_rejects_misspelled_action_field(self) -> None:
        script = load_script("tomb_entrance")
        use = script["entities"]["left_door"]["metadata"]["actions"]["use"]
        use["required_tool"] = use.pop("required_tools")

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("unsupported action field: required_tool", str(context.exception))

    def test_validate_script_rejects_non_canonical_action_key(self) -> None:
        script = load_script("tomb_entrance")
        actions = script["entities"]["left_door"]["metadata"]["actions"]
        actions["burn"] = actions.pop("use")
        script["entities"]["left_door"]["metadata"]["allowed_actions"] = ["open", "burn", "inspect"]

        with self.assertRaises(ValueError) as context:
            validate_script(script)

        self.assertIn("non-canonical action: burn", str(context.exception))

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
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        action = {"type": "inspect", "target": "左门", "method": "", "tool": ""}
        self.assertTrue(validate(action, game.state)["valid"])

        action_spec = get_action_spec(action, game.state)

        self.assertEqual(action_spec["dc"], 10)
        self.assertIn("flags", action_spec["outcomes"]["success"])

    def test_resolved_action_spec_includes_normalized_context(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        game.state.apply_changes({"player": {"inventory_add": ["铁钥匙"]}})
        action = {
            "type": "burn",
            "target": "铁门",
            "tool": "铁钥匙",
            "method_text": "用铁钥匙开铁门",
        }
        self.assertTrue(validate(action, game.state)["valid"])

        action_spec = resolve_action_spec(action, game.state)

        self.assertEqual(action_spec["intent_family"], "use")
        self.assertEqual(action_spec["scope"], "entity")
        self.assertEqual(action_spec["target_id"], "iron_door")
        self.assertEqual(action_spec["tool_id"], "铁钥匙")
        self.assertEqual(action_spec["dc"], 12)
        self.assertEqual(action_spec["required_tools"], ["铁钥匙"])

    def test_action_spec_uses_scene_action_without_target(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
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
