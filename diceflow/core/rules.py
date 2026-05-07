from __future__ import annotations

import random

from diceflow.core.intent import normalize_action
from diceflow.core.models import Action
from diceflow.core.state import GameState
from diceflow.scripting.resolver import resolve_action_spec
from diceflow.scripting.scene_rules import get_dc_modifier


class RuleEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def resolve(self, action: Action, state: GameState, forced_roll: int | None = None) -> dict[str, int | str]:
        dc = self._dc_for(action, state)
        roll = forced_roll if forced_roll is not None else self.rng.randint(1, 20)

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
        action.update(normalize_action(action, state))
        action_spec = resolve_action_spec(action, state)
        dc = int(action_spec.get("dc", 12))
        dc += get_dc_modifier(action, state)
        return max(5, dc)
