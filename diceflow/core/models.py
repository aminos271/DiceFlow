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
    scene: dict[str, Any]
    player_state: dict[str, Any]


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
