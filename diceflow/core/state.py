from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.scripting.loader import ENTITY_RUNTIME_DEFAULTS, Script, materialize_entity


class GameState:
    def __init__(self, script: Script) -> None:
        self.script = deepcopy(script)
        self.turn_id = 0
        self.player: dict[str, Any] = deepcopy(self.script["player"])
        self.scene: dict[str, Any] = deepcopy(self.script["scene"])
        self.entities: dict[str, dict[str, Any]] = {
            entity_id: self._with_runtime_defaults(entity)
            for entity_id, entity in deepcopy(self.script["entities"]).items()
        }
        self.flags: dict[str, Any] = deepcopy(self.script["flags"])
        self.recent_events: list[str] = []
        self.history: list[dict[str, Any]] = []

    def get_snapshot(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "player": deepcopy(self.player),
            "scene": deepcopy(self.scene),
            "entities": deepcopy(self.entities),
            "flags": deepcopy(self.flags),
            "recent_events": list(self.recent_events[-5:]),
        }

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
            self.entities[entity_id] = self._with_runtime_defaults(materialize_entity(entity, entity_id))

        for entity_id in changes.get("remove_entities", []):
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
            entity["looted"] = True
            entity["available"] = False
            entity["visible"] = False

        for key, value in changes.get("flags", {}).items():
            self.flags[key] = value

        for event in changes.get("events", []):
            self.recent_events.append(str(event))
        self.recent_events = self.recent_events[-10:]

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
