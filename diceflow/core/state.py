from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from diceflow.app.hints import entity_action_hint, get_allowed_actions, scene_action_hint
from diceflow.core.lifecycle import (
    cleanup_expired_entities,
    initialize_entity,
    mark_inventory_item,
    mark_removed_entity,
    note_player_interaction,
    prepare_spawned_entity,
)
from diceflow.core.matching import match_entity_name
from diceflow.core.models import Location, NpcMemory, Thread
from diceflow.core.runtime_patch import RuntimeScriptPatch, apply_runtime_script_patch, normalize_runtime_script_patch
from diceflow.core.utils import dedupe_preserving_order
from diceflow.scripting.archetypes import ENTITY_RUNTIME_DEFAULTS, Script, materialize_entity


class GameState:
    def __init__(self, script: Script | object) -> None:
        # Accept WorldBootstrap and convert to script dict
        script = _ensure_script_dict(script)
        self.base_script = deepcopy(script)
        self.script = deepcopy(script)
        self.script_patches: list[RuntimeScriptPatch] = []
        self.turn_id = 0
        self.player: dict[str, Any] = deepcopy(self.script["player"])
        self.scene: dict[str, Any] = deepcopy(self.script["scene"])
        self.entities: dict[str, dict[str, Any]] = {
            entity_id: initialize_entity(self._with_runtime_defaults(entity), entity_id, self.turn_id)
            for entity_id, entity in deepcopy(self.script["entities"]).items()
        }
        self.flags: dict[str, Any] = deepcopy(self.script["flags"])
        self.recent_events: list[str] = []
        self.history: list[dict[str, Any]] = []
        self.entity_journal: list[dict[str, Any]] = []
        self.threads: dict[str, Thread] = {}
        self.locations: dict[str, Location] = {
            loc_id: Location.from_dict(loc_data) if isinstance(loc_data, dict) else Location(id=loc_id, name=loc_id)
            for loc_id, loc_data in self.script.get("locations", {}).items()
        }
        self.npc_memories: dict[str, NpcMemory] = {}

    def apply_script_patch(self, patch: RuntimeScriptPatch | None) -> None:
        if not patch:
            return

        normalized = normalize_runtime_script_patch(patch)
        existing_entity_ids = set(self.script.get("entities", {})) | set(self.entities)
        for op in normalized["ops"]:
            if op["op"] == "add_entity" and op["id"] in existing_entity_ids:
                raise ValueError(f"runtime script patch cannot overwrite existing entity id: {op['id']}")

        next_script = apply_runtime_script_patch(self.script, normalized)
        added_entities: dict[str, dict[str, Any]] = {}
        for op in normalized["ops"]:
            if op["op"] == "add_entity":
                entity_id = op["id"]
                added_entities[entity_id] = next_script["entities"][entity_id]

        self.script = next_script
        self.script_patches.append(deepcopy(normalized))
        for op in normalized["ops"]:
            if op["op"] == "set_flag":
                self.flags[op["key"]] = op["value"]
            elif op["op"] == "set_scene":
                self.scene = deepcopy(op["scene"])
        for entity_id, entity in added_entities.items():
            self.entities[entity_id] = initialize_entity(
                self._with_runtime_defaults(deepcopy(entity)),
                entity_id,
                self.turn_id,
            )

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "player": deepcopy(self.player),
            "scene": deepcopy(self.scene),
            "entities": deepcopy(self.entities),
            "flags": deepcopy(self.flags),
            "recent_events": list(self.recent_events[-10:]),
            "history": deepcopy(self.history[-20:]),
            "entity_journal": deepcopy(self.entity_journal[-10:]),
            "script_patches": deepcopy(self.script_patches[-10:]),
            "threads": {tid: t.to_dict() for tid, t in self.threads.items()},
            "locations": {lid: l.to_dict() for lid, l in self.locations.items()},
            "npc_memories": {mid: m.to_dict() for mid, m in self.npc_memories.items()},
        }

    def get_visible_entities(self) -> dict[str, dict[str, Any]]:
        return {
            entity_id: deepcopy(entity)
            for entity_id, entity in self.entities.items()
            if self.is_interactable_entity(entity_id)
        }

    def get_hostile_entities(self) -> dict[str, dict[str, Any]]:
        return {
            entity_id: deepcopy(entity)
            for entity_id, entity in self.get_visible_entities().items()
            if entity.get("hostile") or "hostile" in entity.get("tags", [])
        }

    def get_inventory_items(self) -> list[str]:
        return [str(item) for item in self.player.get("inventory", [])]

    def get_current_scene_id(self) -> str:
        return str(
            self.flags.get("runtime.current_scene_id")
            or self.scene.get("id")
            or self.script.get("id")
            or self.scene.get("name")
            or ""
        )

    def get_current_scene(self) -> dict[str, Any]:
        return deepcopy(self.scene)

    def get_exits(self) -> list[dict[str, str]]:
        current_id = self.get_current_scene_id()
        loc = self.locations.get(current_id)
        if not loc or not loc.exits:
            return []
        result: list[dict[str, str]] = []
        for direction, target_id in loc.exits.items():
            target_loc = self.locations.get(target_id)
            result.append({
                "direction": direction,
                "location_id": target_id,
                "location_name": target_loc.name if target_loc else target_id,
            })
        return result

    def get_memories_for_npc(self, npc_entity_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for mem in self.npc_memories.values():
            if mem.npc_entity_id == npc_entity_id and mem.discovered:
                result.append(mem.to_dict())
        result.sort(key=lambda m: m["source_turn_id"], reverse=True)
        return result

    def get_available_action_hints(self) -> list[str]:
        hints: list[str] = []

        for action_type in self.script.get("scene_actions", {}):
            hints.append(scene_action_hint(str(action_type)))

        for entity in self.get_visible_entities().values():
            entity_name = str(entity.get("name") or "目标")
            for action_type in get_allowed_actions(entity):
                hints.append(entity_action_hint(str(action_type), entity_name))

        return dedupe_preserving_order(hints)

    def find_entity_id(self, target: str | None) -> str | None:
        if not target:
            return None

        normalized = target.strip()
        if normalized in self.entities and self.is_interactable_entity(normalized):
            return normalized

        candidates = {
            entity_id: [str(entity.get("name", "")), *[str(a) for a in entity.get("aliases", [])]]
            for entity_id, entity in self.entities.items()
            if self.is_interactable_entity(entity_id)
        }
        return match_entity_name(normalized, candidates)

    def is_interactable_entity(self, entity_id: str) -> bool:
        entity = self.entities.get(entity_id)
        if not entity:
            return False
        return bool(entity.get("visible", True) and entity.get("available", True))

    def find_inventory_item(self, item: str | None) -> str | None:
        if not item:
            return None

        normalized = item.strip()
        for inventory_item in self.player.get("inventory", []):
            if normalized == inventory_item or normalized in inventory_item or inventory_item in normalized:
                return inventory_item
        return None

    def apply_changes(self, changes: dict[str, Any]) -> None:
        if not changes:
            return
        try:
            self.apply_script_patch(changes.get("runtime_script_patch"))
        except (ValueError, KeyError, TypeError) as exc:
            logging.getLogger(__name__).error(
                "apply_script_patch failed (turn %d): %s", self.turn_id, exc, exc_info=True
            )

        player_changes = changes.get("player", {})
        self._apply_object_changes(self.player, player_changes)
        self.player["hp"] = max(0, min(self.player["hp"], self.player["max_hp"]))

        for entity_id, entity in changes.get("spawn_entities", {}).items():
            spawned = self._with_runtime_defaults(materialize_entity(entity, entity_id))
            self.entities[entity_id] = prepare_spawned_entity(
                spawned,
                entity_id,
                self.turn_id,
                origin_kind=str(entity.get("_origin_kind") or "spawned"),
                source_action=str(entity.get("_source_action") or ""),
                source_entity_id=str(entity.get("_source_entity_id") or ""),
                rule_id=str(entity.get("_rule_id") or ""),
            )
            for internal_key in ("_origin_kind", "_source_action", "_source_entity_id", "_rule_id"):
                self.entities[entity_id].pop(internal_key, None)

        for entity_id in changes.get("remove_entities", []):
            entity = self.entities.get(entity_id)
            if entity:
                self.entity_journal.append(mark_removed_entity(entity_id, entity, self.turn_id))
            self.entities.pop(entity_id, None)

        for entity_id in changes.get("reveal_entities", []):
            entity = self.entities.get(entity_id)
            if entity:
                entity["visible"] = True
                entity["available"] = True

        for entity_id, entity_changes in changes.get("entities", {}).items():
            entity = self.entities.get(entity_id)
            if not entity:
                continue
            self._apply_object_changes(entity, entity_changes)
            if "hp" in entity:
                entity["hp"] = max(0, min(entity["hp"], entity.get("max_hp", entity["hp"])))
                if entity["hp"] <= 0:
                    entity["alive"] = False
                    entity["available"] = False
                    entity["hostile"] = False
            self._sync_lifecycle_phase(entity)

        for entity_id, entity_changes in changes.get("set_entity_states", {}).items():
            entity = self.entities.get(entity_id)
            if entity:
                self._apply_object_changes(entity, entity_changes)
                self._sync_lifecycle_phase(entity)

        for entity_id in changes.get("move_item_to_inventory", []):
            entity = self.entities.get(entity_id)
            if not entity or entity.get("looted"):
                continue
            item_name = str(entity.get("item_id") or entity.get("name") or entity_id)
            if item_name not in self.player.setdefault("inventory", []):
                self.player["inventory"].append(item_name)
            mark_inventory_item(entity, self.turn_id)
            entity["looted"] = True
            entity["available"] = False
            entity["visible"] = False

        for key, value in changes.get("flags", {}).items():
            self.flags[key] = value

        for thread_id, thread_data in changes.get("add_thread", {}).items():
            if not isinstance(thread_data, dict):
                continue
            if thread_id in self.threads:
                continue
            thread_data.setdefault("id", thread_id)
            thread_data.setdefault("last_updated_turn_id", self.turn_id)
            thread = Thread.from_dict(thread_data)
            if not thread.title:
                continue
            self.threads[thread_id] = thread

        for thread_id, thread_data in changes.get("update_thread", {}).items():
            if not isinstance(thread_data, dict) or thread_id not in self.threads:
                continue
            thread = self.threads[thread_id]
            if "progress_delta" in thread_data:
                try:
                    progress_delta = int(thread_data["progress_delta"])
                except (TypeError, ValueError):
                    progress_delta = 0
                thread.progress = max(0, min(100, thread.progress + progress_delta))
            if "status" in thread_data:
                value = thread_data["status"]
                if value in Thread.VALID_STATUSES:
                    thread.status = value
                if value == "completed":
                    thread.progress = 100
                elif value == "failed":
                    thread.progress = max(thread.progress, 0)
            if "discovered" in thread_data:
                thread.discovered = bool(thread_data["discovered"])
            if "title" in thread_data:
                thread.title = str(thread_data["title"])
            if "next_hint" in thread_data:
                thread.next_hint = str(thread_data["next_hint"]) if thread_data["next_hint"] else None
            for list_key in ("related_entity_ids", "related_location_ids"):
                if list_key in thread_data:
                    value = thread_data[list_key]
                    existing = getattr(thread, list_key)
                    new_items = [str(i) for i in value] if isinstance(value, list) else []
                    setattr(thread, list_key, list(dict.fromkeys(existing + new_items)))
            thread.last_updated_turn_id = self.turn_id

        for loc_id, loc_data in changes.get("add_location", {}).items():
            if not isinstance(loc_data, dict):
                continue
            if loc_id in self.locations:
                continue
            loc_data.setdefault("id", loc_id)
            loc_data.setdefault("last_visited_turn_id", self.turn_id)
            self.locations[loc_id] = Location.from_dict(loc_data)

        for loc_id, loc_data in changes.get("update_location", {}).items():
            if not isinstance(loc_data, dict) or loc_id not in self.locations:
                continue
            loc = self.locations[loc_id]
            if "name" in loc_data:
                loc.name = str(loc_data["name"])
            if "description" in loc_data:
                loc.description = str(loc_data["description"])
            if "discovered" in loc_data:
                loc.discovered = bool(loc_data["discovered"])
            if "danger_level" in loc_data:
                try:
                    danger_level = int(loc_data["danger_level"])
                except (TypeError, ValueError):
                    danger_level = loc.danger_level
                loc.danger_level = max(0, min(5, danger_level))
            if "exits" in loc_data:
                exits = loc_data["exits"]
                if isinstance(exits, dict):
                    for direction, target_id in exits.items():
                        loc.exits[str(direction)] = str(target_id)
            for list_key in ("related_thread_ids",):
                if list_key in loc_data:
                    existing = getattr(loc, list_key)
                    value = loc_data[list_key]
                    new_items = [str(i) for i in value] if isinstance(value, list) else []
                    setattr(loc, list_key, list(dict.fromkeys(existing + new_items)))
            loc.last_visited_turn_id = self.turn_id

        for mem_id, mem_data in changes.get("add_npc_memory", {}).items():
            if not isinstance(mem_data, dict):
                continue
            actual_id = str(mem_id)
            if actual_id in self.npc_memories:
                actual_id = f"{mem_id}_{self.turn_id}"
            if actual_id in self.npc_memories:
                continue
            mem_data.setdefault("id", actual_id)
            mem_data.setdefault("source_turn_id", self.turn_id)
            mem = NpcMemory.from_dict(mem_data)
            if not mem.npc_entity_id or not mem.summary:
                continue
            mem.id = actual_id
            self.npc_memories[actual_id] = mem

        for mem_id, mem_data in changes.get("update_npc_memory", {}).items():
            if not isinstance(mem_data, dict) or mem_id not in self.npc_memories:
                continue
            mem = self.npc_memories[mem_id]
            if "summary" in mem_data:
                mem.summary = str(mem_data["summary"])
            if "sentiment" in mem_data:
                value = str(mem_data["sentiment"])
                if value in NpcMemory.VALID_SENTIMENTS:
                    mem.sentiment = value
            if "importance" in mem_data:
                try:
                    importance = int(mem_data["importance"])
                except (TypeError, ValueError):
                    importance = mem.importance
                mem.importance = max(0, min(5, importance))
            if "discovered" in mem_data:
                mem.discovered = bool(mem_data["discovered"])
            for list_key in ("tags",):
                if list_key in mem_data:
                    value = mem_data[list_key]
                    new_items = [str(i) for i in value] if isinstance(value, list) else []
                    setattr(mem, list_key, list(dict.fromkeys(mem.tags + new_items)))

        for event in changes.get("events", []):
            self.recent_events.append(str(event))
        self.recent_events = self.recent_events[-10:]

        self.entity_journal.extend(cleanup_expired_entities(self.entities, self.turn_id))
        self.entity_journal = self.entity_journal[-50:]
        self._refresh_end_state()

    def record_turn(self, record: dict[str, Any]) -> None:
        self.history.append(record)
        self.history = self.history[-30:]

    def advance_turn(self) -> int:
        self.turn_id += 1
        return self.turn_id

    def note_player_interaction(self, action: dict[str, Any]) -> None:
        for field in ("target_id", "tool_id"):
            entity_id = self._resolve_entity_reference(action.get(field))
            if entity_id and entity_id in self.entities:
                note_player_interaction(self.entities[entity_id], self.turn_id)

        for field in ("target", "tool"):
            entity_id = self._resolve_entity_reference(action.get(field))
            if entity_id and entity_id in self.entities:
                note_player_interaction(self.entities[entity_id], self.turn_id)

    def update_entity(self, entity_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        entity = self.entities.get(entity_id)
        if not entity:
            raise KeyError(entity_id)
        sanitized = deepcopy(patch)
        sanitized.pop("id", None)
        sanitized.pop("lifecycle", None)
        self._apply_object_changes(entity, sanitized)
        if "hp" in entity:
            entity["hp"] = max(0, min(entity["hp"], entity.get("max_hp", entity["hp"])))
            if entity["hp"] <= 0:
                entity["alive"] = False
        note_player_interaction(entity, self.turn_id)
        self._sync_lifecycle_phase(entity)
        return deepcopy(entity)

    def _apply_object_changes(self, target: dict[str, Any], changes: dict[str, Any]) -> None:
        for key, value in changes.items():
            if key.endswith("_delta"):
                base_key = key.removesuffix("_delta")
                target[base_key] = target.get(base_key, 0) + value
            elif key == "inventory_add":
                for item in value:
                    if item not in target.setdefault("inventory", []):
                        target["inventory"].append(item)
            elif key == "inventory_remove":
                target["inventory"] = [item for item in target.get("inventory", []) if item not in value]
            else:
                target[key] = value

    def _with_runtime_defaults(self, entity: dict[str, Any]) -> dict[str, Any]:
        normalized = {**ENTITY_RUNTIME_DEFAULTS, **entity}
        if normalized.get("destroyed"):
            normalized["available"] = bool(entity.get("available", False))
        return normalized

    def _sync_lifecycle_phase(self, entity: dict[str, Any]) -> None:
        lifecycle = entity.get("lifecycle")
        if not isinstance(lifecycle, dict):
            return
        if entity.get("looted"):
            lifecycle["phase"] = "inventory"
        elif entity.get("destroyed"):
            lifecycle["phase"] = "destroyed"
        elif not entity.get("visible", True) or not entity.get("available", True):
            lifecycle["phase"] = "hidden"
        else:
            lifecycle["phase"] = "active"
        lifecycle["updated_turn_id"] = self.turn_id

    def _resolve_entity_reference(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized in self.entities:
            return normalized
        entity_id = self.find_entity_id(normalized)
        if entity_id:
            return entity_id
        inventory_item = self.find_inventory_item(normalized)
        if not inventory_item:
            return None
        for entity_id, entity in self.entities.items():
            item_name = str(entity.get("item_id") or entity.get("name") or entity_id)
            if item_name == inventory_item:
                return entity_id
        return None

    def _refresh_end_state(self) -> None:
        for condition in self.script.get("ending_conditions", []):
            if self._matches_ending_condition(condition.get("when", {})):
                self.flags["game_over"] = True
                self.flags["ending"] = condition["ending"]
                return

    def _matches_ending_condition(self, when: dict[str, Any]) -> bool:
        if "player_hp_lte" in when and self.player["hp"] > when["player_hp_lte"]:
            return False
        if "turn_id_gte" in when and self.turn_id < when["turn_id_gte"]:
            return False

        for flag, expected in when.get("flags", {}).items():
            if self.flags.get(flag) != expected:
                return False

        for entity_id, expected_values in when.get("entities", {}).items():
            entity = self.entities.get(entity_id, {})
            for key, expected in expected_values.items():
                if entity.get(key) != expected:
                    return False
        return True


def _ensure_script_dict(script: object) -> dict[str, Any]:
    """Convert a WorldBootstrap to a script dict if needed, materializing entities."""
    # If it's already a script dict (has schema_version), use as-is
    if isinstance(script, dict) and "schema_version" in script:
        return script  # type: ignore[return-value]
    # Otherwise, assume it's a WorldBootstrap
    if hasattr(script, "to_script_dict"):
        script_dict = script.to_script_dict()  # type: ignore[union-attr]
        # Materialize entities through archetypes so they get full defaults
        script_dict["entities"] = {
            entity_id: materialize_entity(entity, entity_id)
            for entity_id, entity in script_dict.get("entities", {}).items()
        }
        return script_dict
    raise TypeError(f"expected Script dict or WorldBootstrap, got {type(script).__name__}")


