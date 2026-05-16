from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


Action = dict[str, Any]
CheckResult = dict[str, Any]
StateChanges = dict[str, Any]


class TurnResolution(TypedDict, total=False):
    """Unified turn summary passed to the narrator.

    Every turn — whether standard, dynamic adjudication, invalid, or
    transition attempt — builds one of these so the narrator has a
    single consistent input shape.
    """

    turn_id: int
    player_input: str
    action: Action
    validation: dict[str, Any]
    check: CheckResult | None
    state_changes: StateChanges
    resolution_kind: str  # "standard" | "dynamic_adjudication" | "invalid" | "transition_attempt"
    reason_tags: list[str]
    visible_npcs: dict[str, dict[str, Any]]
    recent_events: list[str]
    recent_history: list[dict[str, Any]]
    scene: dict[str, Any]
    player_state: dict[str, Any]
    lorebook_entries: list[dict[str, Any]]


@dataclass
class TurnRecord:
    turn_id: int
    player_input: str
    action: Action
    validation: dict[str, Any]
    check: CheckResult | None
    state_changes: StateChanges
    narration: str
    summary: str
    mechanical_results: list[str] = field(default_factory=list)
    resolution_card: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "player_input": self.player_input,
            "action": self.action,
            "validation": self.validation,
            "check": self.check,
            "state_changes": self.state_changes,
            "narration": self.narration,
            "summary": self.summary,
            "mechanical_results": self.mechanical_results,
            "resolution_card": self.resolution_card,
        }


@dataclass
class Thread:
    """A quest, objective, or narrative thread tracked by the game engine."""

    id: str
    title: str
    status: str = "active"
    progress: int = 0
    related_entity_ids: list[str] = field(default_factory=list)
    related_location_ids: list[str] = field(default_factory=list)
    discovered: bool = False
    last_updated_turn_id: int = 0
    next_hint: str | None = None

    VALID_STATUSES = frozenset({"active", "completed", "failed"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "progress": self.progress,
            "related_entity_ids": list(self.related_entity_ids),
            "related_location_ids": list(self.related_location_ids),
            "discovered": self.discovered,
            "last_updated_turn_id": self.last_updated_turn_id,
            "next_hint": self.next_hint,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Thread":
        status = str(data.get("status", "active"))
        if status not in Thread.VALID_STATUSES:
            status = "active"
        return Thread(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            status=status,
            progress=_clamp_int(data.get("progress", 0), 0, 100),
            related_entity_ids=_string_list(data.get("related_entity_ids", [])),
            related_location_ids=_string_list(data.get("related_location_ids", [])),
            discovered=bool(data.get("discovered", False)),
            last_updated_turn_id=max(0, _clamp_int(data.get("last_updated_turn_id", 0), 0, 999999)),
            next_hint=str(data["next_hint"]) if data.get("next_hint") else None,
        )


@dataclass
class Location:
    id: str
    name: str
    description: str = ""
    discovered: bool = False
    exits: dict[str, str] = field(default_factory=dict)  # direction_name -> location_id
    danger_level: int = 0
    related_thread_ids: list[str] = field(default_factory=list)
    last_visited_turn_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "discovered": self.discovered,
            "exits": dict(self.exits),
            "danger_level": self.danger_level,
            "related_thread_ids": list(self.related_thread_ids),
            "last_visited_turn_id": self.last_visited_turn_id,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Location":
        return Location(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            discovered=bool(data.get("discovered", False)),
            exits=_string_to_string_dict(data.get("exits", {})),
            danger_level=_clamp_int(data.get("danger_level", 0), 0, 5),
            related_thread_ids=_string_list(data.get("related_thread_ids", [])),
            last_visited_turn_id=_clamp_int(data.get("last_visited_turn_id", 0), 0, 999999),
        )


def _string_to_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
