from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.models import Action, CheckResult, StateChanges
from diceflow.script import get_entity_action
from diceflow.state import GameState


def update_state(action: Action, check: CheckResult, state: GameState) -> StateChanges:
    action_type = str(action.get("type") or "unknown")
    result = str(check.get("result"))
    action_def = _get_action_def(action, state)
    outcomes = action_def.get("outcomes", {})

    if result in outcomes:
        return _expand_placeholders(outcomes[result], action)
    if "fail" in outcomes:
        return _expand_placeholders(outcomes["fail"], action)

    return {
        "player": {"hp_delta": -1},
        "events": ["迟疑让守卫抢占了位置，你被逼退并擦伤。"],
    }


def _get_action_def(action: Action, state: GameState) -> dict[str, Any]:
    action_type = str(action.get("type") or "unknown")
    target_id = action.get("target_id")
    if target_id and target_id in state.entities:
        return get_entity_action(state.script, state.entities[target_id], action_type)
    return state.script.get("scene_actions", {}).get(action_type, {})


def _expand_placeholders(changes: StateChanges, action: Action) -> StateChanges:
    expanded = deepcopy(changes)
    target_id = action.get("target_id")
    if target_id and "$target" in expanded.get("entities", {}):
        expanded["entities"][target_id] = expanded["entities"].pop("$target")
    return expanded
