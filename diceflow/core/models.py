from __future__ import annotations

from dataclasses import dataclass
from typing import Any


Action = dict[str, Any]
CheckResult = dict[str, Any]
StateChanges = dict[str, Any]


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
        }

