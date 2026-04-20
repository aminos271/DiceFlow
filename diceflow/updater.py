from __future__ import annotations

from copy import deepcopy

from diceflow.models import Action, CheckResult, StateChanges
from diceflow.script import get_action_spec
from diceflow.state import GameState


def update_state(action: Action, check: CheckResult, state: GameState) -> StateChanges:
    result = str(check.get("result"))
    action_spec = get_action_spec(action, state)
    outcomes = action_spec.get("outcomes", {})

    if result in outcomes:
        return _expand_placeholders(outcomes[result], action)
    if "fail" in outcomes:
        return _expand_placeholders(outcomes["fail"], action)

    return {
        "player": {"hp_delta": -1},
        "events": ["迟疑让守卫抢占了位置，你被逼退并擦伤。"],
    }


def _expand_placeholders(changes: StateChanges, action: Action) -> StateChanges:
    expanded = deepcopy(changes)
    target_id = action.get("target_id")
    if target_id and "$target" in expanded.get("entities", {}):
        expanded["entities"][target_id] = expanded["entities"].pop("$target")
    return expanded
