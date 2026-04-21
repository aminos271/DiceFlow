from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from typing import Any

from diceflow.core.intent import CANONICAL_INTENT_FAMILIES, action_family
from diceflow.core.models import Action


Script = dict[str, Any]
ENTITY_RUNTIME_DEFAULTS = {
    "visible": True,
    "available": True,
    "destroyed": False,
    "opened": False,
    "looted": False,
}
ENTITY_ARCHETYPES: dict[str, dict[str, Any]] = {
    "container": {
        **ENTITY_RUNTIME_DEFAULTS,
        "contents": [],
        "hooks": {
            "open_critical_success_events": ["你打开了$target_name，里面的东西显露出来。"],
            "open_success_events": ["你打开了$target_name，里面的东西显露出来。"],
            "open_fail_events": ["$target_name卡住了，但你觉得还能再试。"],
            "open_critical_fail_events": ["$target_name突然破裂，碎片划伤了你。"],
            "inspect_success_events": ["你确认$target_name可能藏有物品。"],
        },
        "metadata": {
            "allowed_actions": ["open", "inspect"],
            "actions": {
                "open": {
                    "dc": 10,
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"opened": True}},
                            "reveal_entities": "$contents",
                            "events": "$hook.open_critical_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"opened": True}},
                            "reveal_entities": "$contents",
                            "events": "$hook.open_success_events",
                        },
                        "fail": {
                            "events": "$hook.open_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "events": "$hook.open_critical_fail_events",
                        },
                    },
                },
                "inspect": {
                    "dc": 8,
                    "outcomes": {
                        "success": {
                            "events": "$hook.inspect_success_events",
                        }
                    },
                },
            },
        },
    },
    "door": {
        **ENTITY_RUNTIME_DEFAULTS,
        "locked": True,
        "hooks": {
            "required_tools": [],
            "open_flags": {},
            "use_flags": {},
            "open_critical_success_events": ["$target_name被你顺利打开。"],
            "open_success_events": ["$target_name被打开。"],
            "open_fail_events": ["$target_name卡住了，你需要再试一次。"],
            "open_critical_fail_events": ["你用力过猛，被$target_name反震擦伤。"],
            "use_critical_success_events": ["你用工具顺利打开了$target_name。"],
            "use_success_events": ["工具生效，$target_name被打开。"],
            "use_fail_events": ["工具卡住了，你需要调整角度再试一次。"],
            "use_critical_fail_events": ["你用力过猛，工具滑脱划伤手指。"],
            "inspect_success_events": ["你检查了$target_name。"],
        },
        "metadata": {
            "allowed_actions": ["open", "use", "inspect"],
            "actions": {
                "open": {
                    "dc": 12,
                    "required_tools": "$hook.required_tools",
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.open_flags",
                            "events": "$hook.open_critical_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.open_flags",
                            "events": "$hook.open_success_events",
                        },
                        "fail": {
                            "events": "$hook.open_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "events": "$hook.open_critical_fail_events",
                        },
                    },
                },
                "use": {
                    "dc": 12,
                    "required_tools": "$hook.required_tools",
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.use_flags",
                            "events": "$hook.use_critical_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.use_flags",
                            "events": "$hook.use_success_events",
                        },
                        "fail": {
                            "events": "$hook.use_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "events": "$hook.use_critical_fail_events",
                        },
                    },
                },
                "inspect": {
                    "dc": 8,
                    "outcomes": {
                        "success": {
                            "events": "$hook.inspect_success_events",
                        }
                    },
                },
            },
        },
    },
    "pickup": {
        **ENTITY_RUNTIME_DEFAULTS,
        "hooks": {
            "take_flags": {},
            "take_critical_success_events": ["你立刻捡起$target_name并收好。"],
            "take_success_events": ["你拿起$target_name并收好。"],
            "take_fail_events": ["$target_name暂时卡住了，你需要再试一次。"],
            "inspect_success_events": ["你检查了$target_name。"],
        },
        "metadata": {
            "allowed_actions": ["take", "inspect"],
            "actions": {
                "take": {
                    "dc": 5,
                    "outcomes": {
                        "critical_success": {
                            "move_item_to_inventory": ["$target"],
                            "flags": "$hook.take_flags",
                            "events": "$hook.take_critical_success_events",
                        },
                        "success": {
                            "move_item_to_inventory": ["$target"],
                            "flags": "$hook.take_flags",
                            "events": "$hook.take_success_events",
                        },
                        "fail": {
                            "events": "$hook.take_fail_events",
                        },
                    },
                },
                "inspect": {
                    "dc": 5,
                    "outcomes": {
                        "success": {
                            "events": "$hook.inspect_success_events",
                        }
                    },
                },
            },
        },
    },
}
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
OPTIONAL_TOP_LEVEL_TYPES = {
    "action_rules": list,
    "dc_modifiers": list,
    "ending_texts": dict,
    "default_no_outcome_event": str,
}


def load_script(script_name: str) -> Script:
    module = import_module(f"diceflow.content.scripts.{script_name}")
    script = deepcopy(module.SCRIPT)
    materialize_script(script)
    validate_script(script)
    return script


def materialize_script(script: Script) -> Script:
    script["entities"] = {
        entity_id: materialize_entity(entity, entity_id)
        for entity_id, entity in script.get("entities", {}).items()
    }
    return script


def materialize_entity(entity: dict[str, Any], entity_id: str | None = None) -> dict[str, Any]:
    entity_type = str(entity.get("type") or "")
    base = deepcopy(ENTITY_ARCHETYPES.get(entity_type, ENTITY_RUNTIME_DEFAULTS))
    merged = _deep_merge(base, deepcopy(entity))
    return _render_entity_templates(merged, entity_id)


def get_entity_action(script: Script, entity: dict[str, Any], action_type: str) -> dict[str, Any]:
    return entity.get("metadata", {}).get("actions", {}).get(action_type, {})


def get_allowed_actions(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if "allowed_actions" in metadata:
        return list(metadata["allowed_actions"])
    return list(metadata.get("actions", {}).keys())


def resolve_action_spec(action: Action, state: Any) -> dict[str, Any]:
    action_type = action_family(action)
    target_id = str(action.get("target_id") or "")
    tool_id = str(action.get("tool_id") or "")
    scope = "scene"
    action_spec: dict[str, Any] = {}

    if target_id and target_id in state.entities:
        entity = state.entities[target_id]
        entity_action = get_entity_action(state.script, entity, action_type)
        if entity_action:
            scope = "entity"
            action_spec = entity_action
    if not action_spec:
        action_spec = state.script.get("scene_actions", {}).get(action_type, {})

    return {
        **action_spec,
        "intent_family": action_type,
        "scope": scope,
        "target_id": target_id,
        "tool_id": tool_id,
    }


def get_action_spec(action: Action, state: Any) -> dict[str, Any]:
    return resolve_action_spec(action, state)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _render_entity_templates(entity: dict[str, Any], entity_id: str | None) -> dict[str, Any]:
    context = {
        "entity_id": entity_id or "",
        "target_name": str(entity.get("name") or entity_id or "目标"),
        "contents": list(entity.get("contents", [])),
        "hook": entity.get("hooks", {}),
        "item_id": entity.get("item_id") or entity.get("name") or entity_id or "",
    }
    return _render_template_value(entity, context)


def _render_template_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if value == "$contents":
            return list(context["contents"])
        if value == "$item_id":
            return context["item_id"]
        if value.startswith("$hook."):
            return deepcopy(_lookup_path(context["hook"], value.removeprefix("$hook.")))
        return value.replace("$target_name", str(context["target_name"]))
    if isinstance(value, list):
        return [_render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {
            str(_render_template_value(key, context)): _render_template_value(item, context)
            for key, item in value.items()
        }
    return value


def _lookup_path(source: Any, path: str) -> Any:
    current = source
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return {}
        current = current[part]
    return current


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

    for key, expected_type in OPTIONAL_TOP_LEVEL_TYPES.items():
        if key in script and not isinstance(script[key], expected_type):
            errors.append(f"{key} must be a {expected_type.__name__}")


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

    if "spawn_entities" in changes and not isinstance(changes["spawn_entities"], dict):
        errors.append(f"{path}.spawn_entities must be a dict")
    if "remove_entities" in changes and not isinstance(changes["remove_entities"], list):
        errors.append(f"{path}.remove_entities must be a list")
    if "reveal_entities" in changes and not isinstance(changes["reveal_entities"], list):
        errors.append(f"{path}.reveal_entities must be a list")
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
