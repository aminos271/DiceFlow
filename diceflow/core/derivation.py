from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action, CheckResult, StateChanges


DEFAULT_IMPLIED_TEMPLATES: dict[str, dict[str, Any]] = {
    "shield": {
        "id_template": "$source_id_shield",
        "entity": {
            "name": "shield",
            "aliases": ["shield"],
            "type": "pickup",
            "tags": ["equipment", "shield", "implied", "derived"],
            "lifecycle": {
                "category": "derived",
                "cleanup": {"policy": "never"},
            },
        },
    },
}


def derive_state_changes(
    action: Action,
    check: CheckResult,
    explicit_changes: StateChanges,
    state: Any,
) -> StateChanges:
    derived_changes: StateChanges = {}
    for rule in state.script.get("derivation_rules", []):
        if not _matches_rule(rule, action, check, explicit_changes, state):
            continue
        _merge_changes(derived_changes, _changes_for_rule(rule, action, state, explicit_changes))

    if not derived_changes:
        return explicit_changes

    merged = deepcopy(explicit_changes)
    _merge_changes(merged, derived_changes)
    return merged


def resolve_implied_entity(action: Action, state: Any) -> str:
    target_text = str(action.get("target") or "").strip()
    if not target_text:
        return ""

    for source_id, source in state.entities.items():
        if not state.is_interactable_entity(source_id):
            continue
        for implied in _iter_implied_specs(source):
            template = _resolve_implied_template(implied, state)
            entity = _render_implied_entity(template, source_id, source, state)
            if not _matches_implied_target(target_text, entity, implied):
                continue

            entity_id = _render_source_template(
                str(template.get("id_template") or f"{source_id}_{_implied_kind(implied)}"),
                source_id,
                source,
                state,
            )
            if not entity_id:
                continue
            existing_id = state.find_entity_id(entity_id) or state.find_entity_id(str(entity.get("name") or ""))
            if existing_id:
                return existing_id

            entity["_origin_kind"] = "derived"
            entity["_source_action"] = action_family(action)
            entity["_source_entity_id"] = source_id
            entity["_rule_id"] = f"implied:{_implied_kind(implied)}"
            state.apply_changes({"spawn_entities": {entity_id: entity}})
            return entity_id
    return ""


def _matches_rule(
    rule: dict[str, Any],
    action: Action,
    check: CheckResult,
    explicit_changes: StateChanges,
    state: Any,
) -> bool:
    when = rule.get("when", {})
    if not isinstance(when, dict):
        return False

    if "result" in when and not _matches_value(str(check.get("result") or ""), when["result"]):
        return False

    family = action_family(action)
    if "intent_family" in when and not _matches_value(family, when["intent_family"]):
        return False

    target_id = str(action.get("target_id") or "")
    target = _projected_target(target_id, explicit_changes, state)
    if "target_id" in when and not _matches_value(target_id, when["target_id"]):
        return False
    if "target_type" in when and not _matches_value(str(target.get("type") or ""), when["target_type"]):
        return False
    if "target" in when and not _matches_object(target, when["target"]):
        return False
    if "flags" in when and not _matches_object(state.flags, when["flags"]):
        return False

    target_tags = target.get("tags", [])
    if "target_tags" in when and not _matches_all_tags(target_tags, when["target_tags"]):
        return False
    if "any_target_tags" in when and not _matches_any_tag(target_tags, when["any_target_tags"]):
        return False

    return True


def _changes_for_rule(
    rule: dict[str, Any],
    action: Action,
    state: Any,
    explicit_changes: StateChanges,
) -> StateChanges:
    spawn = rule.get("spawn")
    if not isinstance(spawn, dict):
        return {}

    target_id = str(action.get("target_id") or "")
    target = _projected_target(target_id, explicit_changes, state)
    entity_id = _render_template(str(spawn.get("id_template") or ""), target_id, target, state)
    if not entity_id:
        return {}
    if entity_id in state.entities or entity_id in explicit_changes.get("spawn_entities", {}):
        return {}

    entity_template = deepcopy(spawn.get("entity", {}))
    if not isinstance(entity_template, dict):
        return {}

    entity = _render_value(entity_template, target_id, target, state)
    entity["_origin_kind"] = "derived"
    entity["_source_action"] = action_family(action)
    entity["_source_entity_id"] = target_id
    entity["_rule_id"] = str(rule.get("id") or "")

    return {"spawn_entities": {entity_id: entity}}


def _iter_implied_specs(source: dict[str, Any]) -> list[Any]:
    specs: list[Any] = []
    for key in ("implied_equipment", "implied_entities"):
        value = source.get(key, [])
        if isinstance(value, list):
            specs.extend(value)
    return specs


def _resolve_implied_template(implied: Any, state: Any) -> dict[str, Any]:
    if isinstance(implied, dict) and "entity" in implied:
        return deepcopy(implied)

    kind = _implied_kind(implied)
    templates = state.script.get("implied_entity_templates", {})
    if isinstance(templates, dict) and isinstance(templates.get(kind), dict):
        return deepcopy(templates[kind])
    return deepcopy(DEFAULT_IMPLIED_TEMPLATES.get(kind, {}))


def _render_implied_entity(
    template: dict[str, Any],
    source_id: str,
    source: dict[str, Any],
    state: Any,
) -> dict[str, Any]:
    entity = template.get("entity", {})
    if not isinstance(entity, dict):
        entity = {}
    return _render_source_value(entity, source_id, source, state)


def _matches_implied_target(target_text: str, entity: dict[str, Any], implied: Any) -> bool:
    names = [
        _implied_kind(implied),
        str(entity.get("name") or ""),
        *[str(alias) for alias in entity.get("aliases", [])],
        *[str(tag) for tag in entity.get("tags", [])],
    ]
    normalized = target_text.lower()
    return any(name and (normalized in name.lower() or name.lower() in normalized) for name in names)


def _implied_kind(implied: Any) -> str:
    if isinstance(implied, str):
        return implied
    if isinstance(implied, dict):
        return str(implied.get("kind") or implied.get("id") or implied.get("name") or "")
    return ""


def _projected_target(target_id: str, explicit_changes: StateChanges, state: Any) -> dict[str, Any]:
    target = deepcopy(state.entities.get(target_id, {}))
    for changes_key in ("entities", "set_entity_states"):
        changes = explicit_changes.get(changes_key, {})
        if isinstance(changes, dict) and isinstance(changes.get(target_id), dict):
            _apply_projection(target, changes[target_id])
    if target.get("hp", 1) <= 0:
        target["alive"] = False
    return target


def _apply_projection(target: dict[str, Any], changes: dict[str, Any]) -> None:
    for key, value in changes.items():
        if key.endswith("_delta"):
            base_key = key.removesuffix("_delta")
            target[base_key] = target.get(base_key, 0) + value
        else:
            target[key] = value


def _merge_changes(target: StateChanges, source: StateChanges) -> None:
    for key, value in source.items():
        if key in {"entities", "flags", "spawn_entities", "set_entity_states"} and isinstance(value, dict):
            target.setdefault(key, {})
            for child_key, child_value in value.items():
                if isinstance(child_value, dict) and isinstance(target[key].get(child_key), dict):
                    target[key][child_key].update(deepcopy(child_value))
                else:
                    target[key][child_key] = deepcopy(child_value)
        elif key in {"events", "remove_entities", "reveal_entities", "move_item_to_inventory"} and isinstance(value, list):
            target.setdefault(key, [])
            for item in value:
                if item not in target[key]:
                    target[key].append(deepcopy(item))
        else:
            target[key] = deepcopy(value)


def _render_value(value: Any, target_id: str, target: dict[str, Any], state: Any) -> Any:
    if isinstance(value, str):
        return _render_template(value, target_id, target, state)
    if isinstance(value, list):
        return [_render_value(item, target_id, target, state) for item in value]
    if isinstance(value, dict):
        return {
            str(_render_value(key, target_id, target, state)): _render_value(item, target_id, target, state)
            for key, item in value.items()
        }
    return value


def _render_template(value: str, target_id: str, target: dict[str, Any], state: Any) -> str:
    return (
        value.replace("$target_id", target_id)
        .replace("$target_name", str(target.get("name") or target_id))
        .replace("$material", str(target.get("material") or "object"))
        .replace("$turn_id", str(getattr(state, "turn_id", 0)))
    )


def _render_source_value(value: Any, source_id: str, source: dict[str, Any], state: Any) -> Any:
    if isinstance(value, str):
        return _render_source_template(value, source_id, source, state)
    if isinstance(value, list):
        return [_render_source_value(item, source_id, source, state) for item in value]
    if isinstance(value, dict):
        return {
            str(_render_source_value(key, source_id, source, state)): _render_source_value(item, source_id, source, state)
            for key, item in value.items()
        }
    return value


def _render_source_template(value: str, source_id: str, source: dict[str, Any], state: Any) -> str:
    return (
        value.replace("$source_id", source_id)
        .replace("$source_name", str(source.get("name") or source_id))
        .replace("$turn_id", str(getattr(state, "turn_id", 0)))
    )


def _matches_value(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def _matches_object(actual: dict[str, object], expected: object) -> bool:
    if not isinstance(expected, dict):
        return False
    for key, expected_value in expected.items():
        if actual.get(str(key)) != expected_value:
            return False
    return True


def _matches_all_tags(entity_tags: object, required_tags: object) -> bool:
    tags = entity_tags if isinstance(entity_tags, list) else []
    if isinstance(required_tags, str):
        required_tags = [required_tags]
    elif not isinstance(required_tags, list):
        return False
    return all(tag in tags for tag in required_tags)


def _matches_any_tag(entity_tags: object, required_tags: object) -> bool:
    tags = entity_tags if isinstance(entity_tags, list) else []
    if isinstance(required_tags, str):
        required_tags = [required_tags]
    elif not isinstance(required_tags, list):
        return False
    return any(tag in tags for tag in required_tags)
