from __future__ import annotations

import random

from diceflow.models import Action
from diceflow.state import GameState


DEFAULT_DC = {
    "attack": 12,
    "open": 14,
    "burn": 10,
    "inspect": 10,
    "talk": 13,
    "flee": 12,
    "wait": 8,
    "unknown": 12,
}


class RuleEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def resolve(self, action: Action, state: GameState) -> dict[str, int | str]:
        action_type = str(action.get("type") or "unknown")
        dc = self._dc_for(action, state)
        roll = self.rng.randint(1, 20)

        if roll == 1:
            result = "critical_fail"
        elif roll == 20:
            result = "critical_success"
        elif roll >= dc:
            result = "success"
        else:
            result = "fail"

        return {"dc": dc, "roll": roll, "result": result}

    def _dc_for(self, action: Action, state: GameState) -> int:
        action_type = str(action.get("type") or "unknown")
        dc = DEFAULT_DC.get(action_type, 12)

        if action_type == "open" and state.entities["left_door"].get("weakened"):
            dc -= 3
        if action_type == "attack" and not state.entities["guard_1"].get("hostile", True):
            dc -= 2
        return max(5, dc)

