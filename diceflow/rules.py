from __future__ import annotations

import random

from diceflow.models import Action
from diceflow.script import resolve_action_spec
from diceflow.script_rules import get_dc_modifier
from diceflow.state import GameState


class RuleEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def resolve(self, action: Action, state: GameState) -> dict[str, int | str]:
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
        action_spec = resolve_action_spec(action, state)
        dc = int(action_spec.get("dc", 12))
        dc += get_dc_modifier(action, state)
        return max(5, dc)
