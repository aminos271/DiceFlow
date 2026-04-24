from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.utils import deep_merge


DEFAULT_CLEANUP = {"policy": "never"}


def initialize_entity(entity: dict[str, Any], entity_id: str, turn_id: int = 0) -> dict[str, Any]:
    """Attach lifecycle metadata to script-defined entities without changing gameplay fields."""
    initialized = deepcopy(entity)
    lifecycle = _merged_lifecycle(
        initialized.get("lifecycle"),
        category="persistent",
        phase=_phase_for_entity(initialized),
        origin={
            "kind": "script",
            "turn_id": turn_id,
            "entity_id": entity_id,
        },
    )
    initialized["lifecycle"] = lifecycle
    return initialized


def prepare_spawned_entity(
    entity: dict[str, Any],
    entity_id: str,
    turn_id: int,
    *,
    origin_kind: str = "spawned",
    source_action: str = "",
    source_entity_id: str = "",
    rule_id: str = "",
) -> dict[str, Any]:
    spawned = deepcopy(entity)
    lifecycle = _merged_lifecycle(
        spawned.get("lifecycle"),
        category=str(spawned.get("lifecycle", {}).get("category") or "temporary"),
        phase=_phase_for_entity(spawned),
        origin={
            "kind": origin_kind,
            "turn_id": turn_id,
            "entity_id": entity_id,
            "source_action": source_action,
            "source_entity_id": source_entity_id,
            "rule_id": rule_id,
        },
    )
    spawned["lifecycle"] = lifecycle
    return spawned


def mark_inventory_item(entity: dict[str, Any], turn_id: int) -> None:
    lifecycle = _merged_lifecycle(
        entity.get("lifecycle"),
        category=str(entity.get("lifecycle", {}).get("category") or "persistent"),
        phase="inventory",
        origin=entity.get("lifecycle", {}).get("origin", {}),
    )
    lifecycle["phase"] = "inventory"
    lifecycle["holder"] = "player"
    lifecycle["updated_turn_id"] = turn_id
    entity["lifecycle"] = lifecycle


def mark_removed_entity(entity_id: str, entity: dict[str, Any], turn_id: int) -> dict[str, Any]:
    lifecycle = deepcopy(entity.get("lifecycle", {}))
    lifecycle["phase"] = "removed"
    lifecycle["updated_turn_id"] = turn_id
    return {
        "turn_id": turn_id,
        "entity_id": entity_id,
        "name": entity.get("name", entity_id),
        "lifecycle": lifecycle,
    }


def cleanup_expired_entities(entities: dict[str, dict[str, Any]], turn_id: int) -> list[dict[str, Any]]:
    removed: list[dict[str, Any]] = []
    for entity_id, entity in list(entities.items()):
        lifecycle = entity.get("lifecycle", {})
        cleanup = lifecycle.get("cleanup", {})
        if cleanup.get("policy") != "after_turns":
            continue
        if lifecycle.get("phase") == "inventory":
            continue
        ttl_turns = int(cleanup.get("ttl_turns", 0) or 0)
        origin_turn = int(lifecycle.get("origin", {}).get("turn_id", turn_id) or turn_id)
        if ttl_turns > 0 and turn_id - origin_turn >= ttl_turns:
            removed.append(mark_removed_entity(entity_id, entity, turn_id))
            entities.pop(entity_id, None)
    return removed


def _merged_lifecycle(
    lifecycle: object,
    *,
    category: str,
    phase: str,
    origin: dict[str, Any],
) -> dict[str, Any]:
    base = {
        "category": category,
        "phase": phase,
        "origin": origin,
        "cleanup": deepcopy(DEFAULT_CLEANUP),
    }
    if isinstance(lifecycle, dict):
        merged = deep_merge(base, lifecycle)
        if not merged.get("origin"):
            merged["origin"] = origin
        if not merged.get("phase"):
            merged["phase"] = phase
        if not merged.get("category"):
            merged["category"] = category
        return merged
    return base


def _phase_for_entity(entity: dict[str, Any]) -> str:
    if entity.get("looted"):
        return "inventory"
    if entity.get("destroyed"):
        return "destroyed"
    if not entity.get("visible", True) or not entity.get("available", True):
        return "hidden"
    return "active"


