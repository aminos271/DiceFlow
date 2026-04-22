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
    "spawn_entities",
    "remove_entities",
    "reveal_entities",
    "move_item_to_inventory",
    "set_entity_states",
}
VALID_ENDING_KEYS = {"player_hp_lte", "turn_id_gte", "flags", "entities"}
VALID_WHEN_KEYS = {"intent_family", "target_id", "target_type", "target", "flags", "entities", "target_tags", "any_target_tags", "tool_tags", "any_tool_tags"}
VALID_DERIVATION_WHEN_KEYS = {"result", "intent_family", "target_id", "target_type", "target", "flags", "target_tags", "any_target_tags"}
VALID_GENERIC_RULE_KEYS = {"id", "when", *VALID_ACTION_KEYS}
VALID_DERIVATION_RULE_KEYS = {"id", "when", "spawn"}
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
    "intro": str,
    "invalid_action_event": str,
    "generic_rules": list,
    "action_rules": list,
    "dc_modifiers": list,
    "ending_texts": dict,
    "default_no_outcome_event": str,
    "derivation_rules": list,
    "implied_entity_templates": dict,
    "implied_entity_rules": list,
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
