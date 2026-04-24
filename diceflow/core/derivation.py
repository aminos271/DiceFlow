from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.implied_entity import (
    _implied_kind,
    _render_implied_entity,
    _resolve_implied_template,
)
from diceflow.core.intent import action_family
from diceflow.core.matching import matches_all_tags, matches_any_tag, matches_object, matches_value
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.utils import dedupe_preserving_order, traverse_replace


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

    merged = deepcopy(explicit_changes)
    _merge_changes(merged, derived_changes)

    merged = _expand_spawn_implied_entities(merged, state)
    merged = _inherit_source_items_for_spawned_corpses(merged, state)
    return merged



def _expand_spawn_implied_entities(changes: StateChanges, state: Any) -> StateChanges:
    """Eagerly generate implied entities for any newly spawned entities.

    When a state change includes spawn_entities, any spawned entity that carries
    ``implied_equipment`` or ``implied_entities`` fields will have those derived
    items generated immediately (one level deep, no recursion).
    """
    spawns = changes.get("spawn_entities", {})
    if not isinstance(spawns, dict):
        return changes

    additional: dict[str, dict[str, Any]] = {}

    for entity_id, entity in spawns.items():
        if not isinstance(entity, dict):
            continue
        for key in ("implied_equipment", "implied_entities"):
            specs = entity.get(key, [])
            if isinstance(specs, str):
                specs = [specs]
            if not isinstance(specs, list):
                continue
            for spec in specs:
                template = _resolve_implied_template(spec, state)
                if not template or not template.get("entity"):
                    continue
                kind = _implied_kind(spec)
                implied_id = f"{entity_id}_{kind}"
                if implied_id in state.entities or implied_id in spawns or implied_id in additional:
                    continue
                implied_entity = _render_implied_entity(template, entity_id, entity, state)
                implied_entity["_origin_kind"] = "derived"
                implied_entity["_source_action"] = "spawn"
                implied_entity["_source_entity_id"] = entity_id
                implied_entity["_rule_id"] = f"implied:{kind}"
                additional[implied_id] = implied_entity

    if not additional:
        return changes

    result = deepcopy(changes)
    result.setdefault("spawn_entities", {})
    result["spawn_entities"].update(additional)
    return result


def _inherit_source_items_for_spawned_corpses(changes: StateChanges, state: Any) -> StateChanges:
    spawns = changes.get("spawn_entities", {})
    if not isinstance(spawns, dict):
        return changes

    result = deepcopy(changes)
    result.setdefault("set_entity_states", {})

    for corpse_id, corpse in result.get("spawn_entities", {}).items():
        if not isinstance(corpse, dict) or not _is_corpse(corpse):
            continue
        source_id = str(corpse.get("_source_entity_id") or corpse.get("source") or "")
        if not source_id:
            continue

        inherited_item_ids = _source_item_ids(source_id, state)
        if not inherited_item_ids:
            continue

        corpse["source"] = source_id
        corpse["inventory"] = dedupe_preserving_order([*list(corpse.get("inventory", [])), *inherited_item_ids])
        for item_id in inherited_item_ids:
            item_changes = result["set_entity_states"].setdefault(item_id, {})
            item_changes.update(
                {
                    "visible": True,
                    "available": True,
                    "holder_id": str(corpse_id),
                }
            )

    if not result.get("set_entity_states"):
        result.pop("set_entity_states", None)
    return result


def _is_corpse(entity: dict[str, Any]) -> bool:
    return entity.get("type") == "corpse" or "corpse" in entity.get("tags", [])


def _source_item_ids(source_id: str, state: Any) -> list[str]:
    source = state.entities.get(source_id, {})
    item_ids: list[str] = []
    item_ids.extend(_flatten_entity_refs(source.get("inventory", [])))
    item_ids.extend(_flatten_entity_refs(source.get("equipped", {})))
    for entity_id, entity in state.entities.items():
        if str(entity.get("source") or "") == source_id and _is_item_like(entity):
            item_ids.append(str(entity_id))
    return dedupe_preserving_order([item_id for item_id in item_ids if item_id in state.entities])


def _flatten_entity_refs(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        refs: list[str] = []
        for item in value:
            refs.extend(_flatten_entity_refs(item))
        return refs
    if isinstance(value, dict):
        refs: list[str] = []
        for item in value.values():
            refs.extend(_flatten_entity_refs(item))
        return refs
    return []


def _is_item_like(entity: dict[str, Any]) -> bool:
    tags = entity.get("tags", [])
    return entity.get("type") in {"item", "pickup"} or "item" in tags or "equipment" in tags


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

    if "result" in when and not matches_value(str(check.get("result") or ""), when["result"]):
        return False

    family = action_family(action)
    if "intent_family" in when and not matches_value(family, when["intent_family"]):
        return False

    target_id = str(action.get("target_id") or "")
    target = _projected_target(target_id, explicit_changes, state)
    if "target_id" in when and not matches_value(target_id, when["target_id"]):
        return False
    if "target_type" in when and not matches_value(str(target.get("type") or ""), when["target_type"]):
        return False
    if "target" in when and not matches_object(target, when["target"]):
        return False
    if "flags" in when and not matches_object(state.flags, when["flags"]):
        return False

    target_tags = target.get("tags", [])
    if "target_tags" in when and not matches_all_tags(target_tags, when["target_tags"]):
        return False
    if "any_target_tags" in when and not matches_any_tag(target_tags, when["any_target_tags"]):
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
    def _leaf(v: Any) -> Any:
        return _render_template(v, target_id, target, state) if isinstance(v, str) else v
    return traverse_replace(value, _leaf)


def _render_template(value: str, target_id: str, target: dict[str, Any], state: Any) -> str:
    return (
        value.replace("$target_id", target_id)
        .replace("$target_name", str(target.get("name") or target_id))
        .replace("$material", str(target.get("material") or "object"))
        .replace("$turn_id", str(getattr(state, "turn_id", 0)))
    )




