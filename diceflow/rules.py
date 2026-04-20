from __future__ import annotations

import random

from diceflow.models import Action
from diceflow.script import get_entity_action
from diceflow.script_rules import get_dc_modifier
from diceflow.state import GameState


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
        action_def = self._get_action_def(action, state)
        dc = int(action_def.get("dc", 12))
        dc += get_dc_modifier(action, state)
        return max(5, dc)

    def _get_action_def(self, action: Action, state: GameState) -> dict[str, object]:
        action_type = str(action.get("type") or "unknown")
        target_id = action.get("target_id")
        if target_id and target_id in state.entities:
            return get_entity_action(state.script, state.entities[target_id], action_type)
        return state.script.get("scene_actions", {}).get(action_type, {})
