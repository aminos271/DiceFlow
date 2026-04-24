from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.lifecycle import (
    cleanup_expired_entities,
    initialize_entity,
    mark_inventory_item,
    mark_removed_entity,
    prepare_spawned_entity,
)
from diceflow.scripting.archetypes import ENTITY_RUNTIME_DEFAULTS, Script, materialize_entity


class GameState:
    def __init__(self, script: Script) -> None:
        self.script = deepcopy(script)
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

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "player": deepcopy(self.player),
            "scene": deepcopy(self.scene),
            "entities": deepcopy(self.entities),
            "flags": deepcopy(self.flags),
            "recent_events": list(self.recent_events[-5:]),
            "entity_journal": deepcopy(self.entity_journal[-10:]),
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
        return str(self.script.get("id") or self.scene.get("id") or self.scene.get("name") or "")

    def get_current_scene(self) -> dict[str, Any]:
        return deepcopy(self.scene)

    def get_available_action_hints(self) -> list[str]:
        hints: list[str] = []

        for action_type in self.script.get("scene_actions", {}):
            hints.append(_scene_action_hint(str(action_type)))

        for entity in self.get_visible_entities().values():
            entity_name = str(entity.get("name") or "目标")
            for action_type in _get_allowed_actions(entity):
                hints.append(_entity_action_hint(str(action_type), entity_name))

        return _dedupe_preserving_order(hints)

    def find_entity_id(self, target: str | None) -> str | None:
        if not target:
            return None

        normalized = target.strip()
        if normalized in self.entities and self.is_interactable_entity(normalized):
            return normalized

        for entity_id, entity in self.entities.items():
            if not self.is_interactable_entity(entity_id):
                continue
            names = [entity.get("name", ""), *entity.get("aliases", [])]
            if normalized in names:
                return entity_id
            if any(normalized and normalized in name for name in names):
                return entity_id
        return None

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

        for event in changes.get("events", []):
            self.recent_events.append(str(event))
        self.recent_events = self.recent_events[-10:]

        self.entity_journal.extend(cleanup_expired_entities(self.entities, self.turn_id))
        self.entity_journal = self.entity_journal[-50:]
        self._refresh_end_state()

    def record_turn(self, record: dict[str, Any]) -> None:
        self.history.append(record)
        self.history = self.history[-20:]

    def advance_turn(self) -> int:
        self.turn_id += 1
        return self.turn_id

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


def _entity_action_hint(action_type: str, entity_name: str) -> str:
    verb = {
        "attack": "攻击",
        "inspect": "检查",
        "open": "打开",
        "talk": "交谈",
        "take": "拿取",
        "use": "使用道具处理",
        "throw": "投掷道具砸向",
        "interact": "互动",
    }.get(action_type, action_type)
    return f"{verb}{entity_name}"


def _scene_action_hint(action_type: str) -> str:
    return {
        "flee": "撤退/拉开距离",
        "wait": "等待/观察局势",
        "move": "移动/靠近目标",
        "unknown": "尝试其他行动",
    }.get(action_type, action_type)


def _get_allowed_actions(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if "allowed_actions" in metadata:
        return list(metadata["allowed_actions"])
    return list(metadata.get("actions", {}).keys())


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
