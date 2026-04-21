from __future__ import annotations

from copy import deepcopy

from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState
from diceflow.scripting.resolver import resolve_action_spec


def update_state(action: Action, check: CheckResult, state: GameState) -> StateChanges:
    result = str(check.get("result"))
    action_spec = resolve_action_spec(action, state)
    outcomes = action_spec.get("outcomes", {})

    if result in outcomes:
        return _expand_placeholders(outcomes[result], action)
    if "fail" in outcomes:
        return _expand_placeholders(outcomes["fail"], action)

    return {
        "player": {"hp_delta": -1},
        "events": [str(state.script.get("default_no_outcome_event", "行动没有产生明确结果，但局势继续推进。"))],
    }


def _expand_placeholders(changes: StateChanges, action: Action) -> StateChanges:
    expanded = _replace_placeholders(deepcopy(changes), action)
    target_id = action.get("target_id")
    if target_id and "$target" in expanded.get("entities", {}):
        expanded["entities"][target_id] = expanded["entities"].pop("$target")
    return expanded


def _replace_placeholders(value: object, action: Action) -> object:
    if value == "$target":
        return action.get("target_id") or "$target"
    if isinstance(value, list):
        return [_replace_placeholders(item, action) for item in value]
    if isinstance(value, dict):
        replaced = {}
        for key, item in value.items():
            replaced_key = str(_replace_placeholders(key, action))
            if replaced_key == "spawn_entities":
                replaced[replaced_key] = item
            else:
                replaced[replaced_key] = _replace_placeholders(item, action)
        return replaced
    return value
