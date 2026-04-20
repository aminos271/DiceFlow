from __future__ import annotations

from copy import deepcopy
from typing import Any


class GameState:
    def __init__(self) -> None:
        self.turn_id = 0
        self.player: dict[str, Any] = {
            "hp": 10,
            "max_hp": 10,
            "inventory": ["短剑", "火把"],
            "location": "古墓入口",
        }
        self.scene: dict[str, Any] = {
            "name": "古墓入口",
            "description": "昏暗石室里潮气很重。一个守卫挡在左门前，门缝里透出微弱冷光。",
        }
        self.entities: dict[str, dict[str, Any]] = {
            "guard_1": {
                "name": "守卫",
                "aliases": ["守卫", "卫兵", "敌人", "看守"],
                "metadata": {
                    "allowed_actions": ["attack", "talk", "inspect", "flee", "wait"],
                },
                "hp": 6,
                "max_hp": 6,
                "alive": True,
                "location": "入口",
                "hostile": True,
            },
            "left_door": {
                "name": "左门",
                "aliases": ["左门", "门", "石门", "出口"],
                "metadata": {
                    "allowed_actions": ["open", "burn", "inspect", "flee", "wait"],
                },
                "type": "door",
                "locked": True,
                "burnable": True,
                "weakened": False,
            },
        }
        self.flags: dict[str, Any] = {
            "found_exit": False,
            "door_open": False,
            "game_over": False,
            "ending": "",
        }
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
        if normalized in self.entities:
            return normalized

        for entity_id, entity in self.entities.items():
            names = [entity.get("name", ""), *entity.get("aliases", [])]
            if normalized in names:
                return entity_id
            if any(normalized and normalized in name for name in names):
                return entity_id
        return None

    def apply_changes(self, changes: dict[str, Any]) -> None:
        if not changes:
            return

        player_changes = changes.get("player", {})
        self._apply_object_changes(self.player, player_changes)
        self.player["hp"] = max(0, min(self.player["hp"], self.player["max_hp"]))

        for entity_id, entity_changes in changes.get("entities", {}).items():
            entity = self.entities.get(entity_id)
            if not entity:
                continue
            self._apply_object_changes(entity, entity_changes)
            if "hp" in entity:
                entity["hp"] = max(0, min(entity["hp"], entity.get("max_hp", entity["hp"])))
                if entity["hp"] <= 0:
                    entity["alive"] = False

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

    def _refresh_end_state(self) -> None:
        guard_alive = self.entities["guard_1"].get("alive", False)
        door_open = bool(self.flags.get("door_open"))

        if self.player["hp"] <= 0:
            self.flags["game_over"] = True
            self.flags["ending"] = "death"
        elif door_open and not guard_alive:
            self.flags["game_over"] = True
            self.flags["ending"] = "victory"
        elif self.turn_id >= 20:
            self.flags["game_over"] = True
            self.flags["ending"] = "timeout"
