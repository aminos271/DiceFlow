from __future__ import annotations

from typing import Any

from diceflow.core.intent import CANONICAL_INTENT_FAMILIES


Script = dict[str, Any]
SCHEMA_VERSION = 1
VALID_OUTCOME_RESULTS = {"critical_success", "success", "fail", "critical_fail"}
VALID_ACTION_KEYS = {"dc", "required_tools", "outcomes"}
VALID_CHANGE_KEYS = {
    "player",
    "entities",
    "flags",
    "events",
    "runtime_script_patch",
    "spawn_entities",
    "remove_entities",
    "reveal_entities",
    "move_item_to_inventory",
    "set_entity_states",
    "add_thread",
    "update_thread",
    "add_location",
    "update_location",
    "add_npc_memory",
    "update_npc_memory",
}
VALID_ENDING_KEYS = {"player_hp_lte", "turn_id_gte", "flags", "entities"}
VALID_WHEN_KEYS = {"intent_family", "target_id", "target_type", "target", "flags", "entities", "target_tags", "any_target_tags", "tool_tags", "any_tool_tags"}
VALID_DERIVATION_WHEN_KEYS = {"result", "intent_family", "target_id", "target_type", "target", "flags", "target_tags", "any_target_tags"}
VALID_REACTION_WHEN_KEYS = VALID_WHEN_KEYS | {"result", "target_alive", "player_alive", "actor_tags", "any_actor_tags"}
VALID_RUNTIME_GENERATION_WHEN_KEYS = VALID_WHEN_KEYS | {"result"}
VALID_GENERIC_RULE_KEYS = {"id", "when", *VALID_ACTION_KEYS}
VALID_DERIVATION_RULE_KEYS = {"id", "when", "spawn"}
VALID_REACTION_RULE_KEYS = {"id", "actor", "when", "changes"}
VALID_RUNTIME_GENERATION_HOOK_KEYS = {
    "id",
    "when",
    "prompt_hint",
    "allowed_entity_types",
    "max_dc",
}
VALID_WORLD_KEYS = {
    "premise",
    "tone",
    "allowed_scene_types",
    "allowed_entity_types",
    "forbidden",
    "max_runtime_dc",
    "max_new_entities_per_transition",
}
REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "id",
    "title",
    "player",
    "scene",
    "flags",
    "entities",
    "scene_actions",
    "ending_conditions",
}
TOP_LEVEL_TYPES = {
    "schema_version": int,
    "id": str,
    "title": str,
    "player": dict,
    "scene": dict,
    "flags": dict,
    "entities": dict,
    "scene_actions": dict,
    "ending_conditions": list,
}
OPTIONAL_TOP_LEVEL_TYPES = {
    "world_id": str,
    "intro": str,
    "invalid_action_event": str,
    "generic_rules": list,
    "action_rules": list,
    "dc_modifiers": list,
    "ending_texts": dict,
    "default_no_outcome_event": str,
    "derivation_rules": list,
    "reaction_rules": list,
    "implied_entity_templates": dict,
    "implied_entity_rules": list,
    "dynamic_entity_templates": dict,
    "runtime_generation_hooks": list,
    "world": dict,
    "locations": dict,
}


def validate_script(script: Script) -> None:
    errors: list[str] = []
    _validate_top_level(script, errors)

    for entity_id, entity in script.get("entities", {}).items():
        _validate_entity(entity_id, entity, errors)

    for action_type, action_spec in script.get("scene_actions", {}).items():
        if action_type not in CANONICAL_INTENT_FAMILIES:
            errors.append(f"scene_actions has non-canonical action: {action_type}")
        _validate_action_spec(f"scene_actions.{action_type}", action_spec, errors, has_target=False)

    for index, rule in enumerate(script.get("generic_rules", [])):
        _validate_generic_rule(f"generic_rules[{index}]", rule, errors)
    for index, rule in enumerate(script.get("derivation_rules", [])):
        _validate_derivation_rule(f"derivation_rules[{index}]", rule, errors)
    for index, rule in enumerate(script.get("reaction_rules", [])):
        _validate_reaction_rule(f"reaction_rules[{index}]", rule, errors)
    for index, hook in enumerate(script.get("runtime_generation_hooks", [])):
        _validate_runtime_generation_hook(f"runtime_generation_hooks[{index}]", hook, errors)
    if "world" in script:
        _validate_world("world", script["world"], errors)
    for index, rule in enumerate(script.get("action_rules", [])):
        _validate_when_condition(f"action_rules[{index}]", rule.get("when", {}), errors)
    for index, modifier in enumerate(script.get("dc_modifiers", [])):
        _validate_when_condition(f"dc_modifiers[{index}]", modifier.get("when", {}), errors)

    _validate_ending_conditions(script, errors)

    if errors:
        raise ValueError("Invalid script:\n- " + "\n- ".join(errors))


def _validate_top_level(script: Script, errors: list[str]) -> None:
    allowed_keys = REQUIRED_TOP_LEVEL_KEYS | set(OPTIONAL_TOP_LEVEL_TYPES)
    unknown_keys = sorted(set(script) - allowed_keys)
    for key in unknown_keys:
        errors.append(f"unsupported top-level field: {key}")

    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(script))
    for key in missing:
        errors.append(f"missing top-level field: {key}")

    if script.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    for key, expected_type in TOP_LEVEL_TYPES.items():
        if key in script and not isinstance(script[key], expected_type):
            errors.append(f"{key} must be a {expected_type.__name__}")

    for key, expected_type in OPTIONAL_TOP_LEVEL_TYPES.items():
        if key in script and not isinstance(script[key], expected_type):
            errors.append(f"{key} must be a {expected_type.__name__}")


def _validate_entity(entity_id: str, entity: dict[str, Any], errors: list[str]) -> None:
    tags = entity.get("tags")
    if tags is not None:
        if not isinstance(tags, list):
            errors.append(f"entities.{entity_id}.tags must be a list")
        else:
            for i, tag in enumerate(tags):
                if not isinstance(tag, str):
                    errors.append(f"entities.{entity_id}.tags[{i}] must be a string")

    metadata = entity.get("metadata")
    if metadata is None:
        return
    if not isinstance(metadata, dict):
        errors.append(f"entities.{entity_id}.metadata must exist")
        return

    actions = metadata.get("actions")
    if not isinstance(actions, dict):
        errors.append(f"entities.{entity_id}.metadata.actions must exist")
        return

    allowed_actions = metadata.get("allowed_actions", list(actions))
    if not isinstance(allowed_actions, list):
        errors.append(f"entities.{entity_id}.metadata.allowed_actions must be a list")
        return

    for action_type in allowed_actions:
        if action_type not in actions:
            errors.append(f"entities.{entity_id}.metadata.allowed_actions includes undefined action: {action_type}")

    for action_type, action_spec in actions.items():
        if action_type not in CANONICAL_INTENT_FAMILIES:
            errors.append(f"entities.{entity_id}.metadata.actions has non-canonical action: {action_type}")
        _validate_action_spec(f"entities.{entity_id}.metadata.actions.{action_type}", action_spec, errors, has_target=True)


def _validate_action_spec(path: str, action_spec: dict[str, Any], errors: list[str], has_target: bool) -> None:
    unknown_keys = sorted(set(action_spec) - VALID_ACTION_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported action field: {key}")

    if "dc" not in action_spec:
        errors.append(f"{path}.dc is required")
    elif not isinstance(action_spec["dc"], int):
        errors.append(f"{path}.dc must be an int")

    if "required_tools" in action_spec and not isinstance(action_spec["required_tools"], list):
        errors.append(f"{path}.required_tools must be a list")

    outcomes = action_spec.get("outcomes")
    if not isinstance(outcomes, dict):
        errors.append(f"{path}.outcomes is required")
        return

    valid_results = VALID_OUTCOME_RESULTS & set(outcomes)
    if not valid_results:
        errors.append(f"{path}.outcomes must include at least one valid result")

    for result, changes in outcomes.items():
        if result not in VALID_OUTCOME_RESULTS:
            errors.append(f"{path}.outcomes has invalid result: {result}")
        _validate_changes(f"{path}.outcomes.{result}", changes, errors, has_target)


def _validate_generic_rule(path: str, rule: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(rule, dict):
        errors.append(f"{path} must be a dict")
        return
    unknown_keys = sorted(set(rule) - VALID_GENERIC_RULE_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported rule field: {key}")
    if "when" not in rule:
        errors.append(f"{path}.when is required")
    else:
        _validate_when_condition(path, rule["when"], errors)
    action_spec = {key: value for key, value in rule.items() if key not in {"id", "when"}}
    _validate_action_spec(path, action_spec, errors, has_target=True)


def _validate_derivation_rule(path: str, rule: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(rule, dict):
        errors.append(f"{path} must be a dict")
        return
    unknown_keys = sorted(set(rule) - VALID_DERIVATION_RULE_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported derivation field: {key}")
    if "when" not in rule:
        errors.append(f"{path}.when is required")
    else:
        _validate_derivation_when_condition(path, rule["when"], errors)
    spawn = rule.get("spawn")
    if not isinstance(spawn, dict):
        errors.append(f"{path}.spawn must be a dict")
        return
    if not isinstance(spawn.get("id_template"), str):
        errors.append(f"{path}.spawn.id_template must be a string")
    if not isinstance(spawn.get("entity"), dict):
        errors.append(f"{path}.spawn.entity must be a dict")


def _validate_reaction_rule(path: str, rule: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(rule, dict):
        errors.append(f"{path} must be a dict")
        return
    unknown_keys = sorted(set(rule) - VALID_REACTION_RULE_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported reaction field: {key}")
    if "when" not in rule:
        errors.append(f"{path}.when is required")
    else:
        _validate_reaction_when_condition(path, rule["when"], errors)
    actor = rule.get("actor", "target")
    if not isinstance(actor, (str, list)):
        errors.append(f"{path}.actor must be a string or list")
    changes = rule.get("changes")
    if not isinstance(changes, dict):
        errors.append(f"{path}.changes must be a dict")
        return
    _validate_changes(f"{path}.changes", changes, errors, has_target=True)


def _validate_runtime_generation_hook(path: str, hook: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(hook, dict):
        errors.append(f"{path} must be a dict")
        return
    unknown_keys = sorted(set(hook) - VALID_RUNTIME_GENERATION_HOOK_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported hook field: {key}")
    if not isinstance(hook.get("id"), str) or not hook.get("id"):
        errors.append(f"{path}.id is required")
    if "when" not in hook:
        errors.append(f"{path}.when is required")
    else:
        _validate_runtime_generation_when_condition(path, hook["when"], errors)
    if not isinstance(hook.get("prompt_hint"), str):
        errors.append(f"{path}.prompt_hint must be a string")
    allowed = hook.get("allowed_entity_types")
    if not isinstance(allowed, list) or not allowed or not all(isinstance(item, str) for item in allowed):
        errors.append(f"{path}.allowed_entity_types must be a non-empty string list")
    max_dc = hook.get("max_dc", 15)
    if not isinstance(max_dc, int) or max_dc < 5 or max_dc > 30:
        errors.append(f"{path}.max_dc must be an int between 5 and 30")


def _validate_world(path: str, world: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(world, dict):
        errors.append(f"{path} must be a dict")
        return
    unknown_keys = sorted(set(world) - VALID_WORLD_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported world field: {key}")
    if not isinstance(world.get("premise", ""), str):
        errors.append(f"{path}.premise must be a string")
    if not isinstance(world.get("tone", ""), str):
        errors.append(f"{path}.tone must be a string")
    for list_key in ("allowed_scene_types", "allowed_entity_types", "forbidden"):
        value = world.get(list_key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(f"{path}.{list_key} must be a string list")
    max_dc = world.get("max_runtime_dc", 15)
    if not isinstance(max_dc, int) or max_dc < 5 or max_dc > 30:
        errors.append(f"{path}.max_runtime_dc must be an int between 5 and 30")
    max_entities = world.get("max_new_entities_per_transition", 4)
    if not isinstance(max_entities, int) or max_entities < 0 or max_entities > 8:
        errors.append(f"{path}.max_new_entities_per_transition must be an int between 0 and 8")


def _validate_changes(path: str, changes: dict[str, Any], errors: list[str], has_target: bool) -> None:
    if not isinstance(changes, dict):
        errors.append(f"{path} must be a dict")
        return

    unknown_keys = sorted(set(changes) - VALID_CHANGE_KEYS)
    for key in unknown_keys:
        errors.append(f"{path} has unsupported change key: {key}")

    if not has_target and "$target" in changes.get("entities", {}):
        errors.append(f"{path} uses $target without an entity target")

    if "events" in changes and not isinstance(changes["events"], list):
        errors.append(f"{path}.events must be a list")

    if "spawn_entities" in changes and not isinstance(changes["spawn_entities"], dict):
        errors.append(f"{path}.spawn_entities must be a dict")
    if "remove_entities" in changes and not isinstance(changes["remove_entities"], list):
        errors.append(f"{path}.remove_entities must be a list")
    if "reveal_entities" in changes and not isinstance(changes["reveal_entities"], (list, str)):
        errors.append(f"{path}.reveal_entities must be a list or string placeholder")
    if "move_item_to_inventory" in changes and not isinstance(changes["move_item_to_inventory"], list):
        errors.append(f"{path}.move_item_to_inventory must be a list")
    if "set_entity_states" in changes and not isinstance(changes["set_entity_states"], dict):
        errors.append(f"{path}.set_entity_states must be a dict")
    if "add_thread" in changes and not isinstance(changes["add_thread"], dict):
        errors.append(f"{path}.add_thread must be a dict")
    elif isinstance(changes.get("add_thread"), dict):
        _validate_thread_changes(f"{path}.add_thread", changes["add_thread"], errors, is_add=True)
    if "update_thread" in changes and not isinstance(changes["update_thread"], dict):
        errors.append(f"{path}.update_thread must be a dict")
    elif isinstance(changes.get("update_thread"), dict):
        _validate_thread_changes(f"{path}.update_thread", changes["update_thread"], errors, is_add=False)
    if "add_location" in changes and not isinstance(changes["add_location"], dict):
        errors.append(f"{path}.add_location must be a dict")
    if "update_location" in changes and not isinstance(changes["update_location"], dict):
        errors.append(f"{path}.update_location must be a dict")
    if "add_npc_memory" in changes and not isinstance(changes["add_npc_memory"], dict):
        errors.append(f"{path}.add_npc_memory must be a dict")
    if "update_npc_memory" in changes and not isinstance(changes["update_npc_memory"], dict):
        errors.append(f"{path}.update_npc_memory must be a dict")


def _validate_thread_changes(path: str, thread_changes: dict[str, Any], errors: list[str], *, is_add: bool) -> None:
    for thread_id, data in thread_changes.items():
        item_path = f"{path}.{thread_id}"
        if not isinstance(data, dict):
            errors.append(f"{item_path} must be a dict")
            continue
        if is_add and not isinstance(data.get("title"), str):
            errors.append(f"{item_path}.title must be a string")
        if "status" in data and data["status"] not in {"active", "completed", "failed"}:
            errors.append(f"{item_path}.status must be active, completed, or failed")
        if "progress" in data and not isinstance(data["progress"], int):
            errors.append(f"{item_path}.progress must be an int")
        if "progress_delta" in data and not isinstance(data["progress_delta"], int):
            errors.append(f"{item_path}.progress_delta must be an int")
        for list_key in ("related_entity_ids", "related_location_ids"):
            if list_key in data and (
                not isinstance(data[list_key], list)
                or not all(isinstance(item, str) for item in data[list_key])
            ):
                errors.append(f"{item_path}.{list_key} must be a string list")
        if "discovered" in data and not isinstance(data["discovered"], bool):
            errors.append(f"{item_path}.discovered must be a bool")
        if "next_hint" in data and data["next_hint"] is not None and not isinstance(data["next_hint"], str):
            errors.append(f"{item_path}.next_hint must be a string or null")


def _validate_ending_conditions(script: Script, errors: list[str]) -> None:
    for index, condition in enumerate(script.get("ending_conditions", [])):
        path = f"ending_conditions[{index}]"
        if not isinstance(condition, dict):
            errors.append(f"{path} must be a dict")
            continue
        if "ending" not in condition:
            errors.append(f"{path}.ending is required")
        when = condition.get("when")
        if not isinstance(when, dict):
            errors.append(f"{path}.when must be a dict")
            continue
        unknown_keys = sorted(set(when) - VALID_ENDING_KEYS)
        for key in unknown_keys:
            errors.append(f"{path}.when has unsupported key: {key}")

def _validate_when_condition(path: str, when: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(when, dict):
        errors.append(f"{path}.when must be a dict")
        return
    unknown_keys = sorted(set(when) - VALID_WHEN_KEYS)
    for key in unknown_keys:
        errors.append(f"{path}.when has unsupported key: {key}")


def _validate_derivation_when_condition(path: str, when: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(when, dict):
        errors.append(f"{path}.when must be a dict")
        return
    unknown_keys = sorted(set(when) - VALID_DERIVATION_WHEN_KEYS)
    for key in unknown_keys:
        errors.append(f"{path}.when has unsupported key: {key}")


def _validate_reaction_when_condition(path: str, when: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(when, dict):
        errors.append(f"{path}.when must be a dict")
        return
    unknown_keys = sorted(set(when) - VALID_REACTION_WHEN_KEYS)
    for key in unknown_keys:
        errors.append(f"{path}.when has unsupported key: {key}")


def _validate_runtime_generation_when_condition(path: str, when: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(when, dict):
        errors.append(f"{path}.when must be a dict")
        return
    unknown_keys = sorted(set(when) - VALID_RUNTIME_GENERATION_WHEN_KEYS)
    for key in unknown_keys:
        errors.append(f"{path}.when has unsupported key: {key}")
