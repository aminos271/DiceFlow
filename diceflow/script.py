from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from typing import Any

from diceflow.intent import CANONICAL_INTENT_FAMILIES
from diceflow.models import Action


Script = dict[str, Any]
VALID_OUTCOME_RESULTS = {"critical_success", "success", "fail", "critical_fail"}
VALID_ACTION_KEYS = {"dc", "required_tools", "outcomes"}
VALID_CHANGE_KEYS = {"player", "entities", "flags", "events"}
VALID_ENDING_KEYS = {"player_hp_lte", "turn_id_gte", "flags", "entities"}
REQUIRED_TOP_LEVEL_KEYS = {
    "id",
    "title",
    "player",
    "scene",
    "flags",
    "entities",
    "scene_actions",
    "ending_conditions",
}


def load_script(script_name: str) -> Script:
    module = import_module(f"diceflow.scripts.{script_name}")
    script = deepcopy(module.SCRIPT)
    validate_script(script)
    return script


def get_entity_action(script: Script, entity: dict[str, Any], action_type: str) -> dict[str, Any]:
    return entity.get("metadata", {}).get("actions", {}).get(action_type, {})


def get_allowed_actions(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if "allowed_actions" in metadata:
        return list(metadata["allowed_actions"])
    return list(metadata.get("actions", {}).keys())


def get_action_spec(action: Action, state: Any) -> dict[str, Any]:
    action_type = str(action.get("intent_family") or action.get("type") or "unknown")
    target_id = action.get("target_id")
    if target_id and target_id in state.entities:
        entity = state.entities[target_id]
        entity_action = get_entity_action(state.script, entity, action_type)
        if entity_action:
            return entity_action
    return state.script.get("scene_actions", {}).get(action_type, {})


def validate_script(script: Script) -> None:
    errors: list[str] = []
    _validate_top_level(script, errors)

    for entity_id, entity in script.get("entities", {}).items():
        _validate_entity(entity_id, entity, errors)

    for action_type, action_spec in script.get("scene_actions", {}).items():
        if action_type not in CANONICAL_INTENT_FAMILIES:
            errors.append(f"scene_actions has non-canonical action: {action_type}")
        _validate_action_spec(f"scene_actions.{action_type}", action_spec, errors, has_target=False)

    _validate_ending_conditions(script, errors)

    if errors:
        raise ValueError("Invalid script:\n- " + "\n- ".join(errors))


def _validate_top_level(script: Script, errors: list[str]) -> None:
    missing = sorted(REQUIRED_TOP_LEVEL_KEYS - set(script))
    for key in missing:
        errors.append(f"missing top-level field: {key}")

    if not isinstance(script.get("entities", {}), dict):
        errors.append("entities must be a dict")
    if not isinstance(script.get("scene_actions", {}), dict):
        errors.append("scene_actions must be a dict")
    if not isinstance(script.get("ending_conditions", []), list):
        errors.append("ending_conditions must be a list")


def _validate_entity(entity_id: str, entity: dict[str, Any], errors: list[str]) -> None:
    metadata = entity.get("metadata")
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
