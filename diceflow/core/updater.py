from __future__ import annotations

from copy import deepcopy

from diceflow.core.derivation import derive_state_changes
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState
from diceflow.core.utils import traverse_replace
from diceflow.scripting.resolver import resolve_action_spec


def update_state(action: Action, check: CheckResult, state: GameState) -> StateChanges:
    result = str(check.get("result"))
    action_spec = resolve_action_spec(action, state)
    outcomes = action_spec.get("outcomes", {})

    outcome_key = _resolve_outcome_key(result, outcomes)
    if outcome_key:
        changes = _expand_placeholders(outcomes[outcome_key], action, state)
        return derive_state_changes(action, check, changes, state)

    changes = {
        "player": {"hp_delta": -1},
        "events": [str(state.script.get("default_no_outcome_event", "行动没有产生明确结果，但局势继续推进。"))],
    }
    return derive_state_changes(action, check, changes, state)


def _resolve_outcome_key(result: str, outcomes: dict[str, object]) -> str:
    if result in outcomes:
        return result
    fallback_order = {
        "critical_success": ("success",),
        "critical_fail": ("fail",),
    }.get(result, ())
    for key in fallback_order:
        if key in outcomes:
            return key
    return ""


def _expand_placeholders(changes: StateChanges, action: Action, state: GameState) -> StateChanges:
    expanded = _replace_placeholders(deepcopy(changes), action, state)
    target_id = action.get("target_id")
    if target_id and "$target" in expanded.get("entities", {}):
        expanded["entities"][target_id] = expanded["entities"].pop("$target")
    tool_id = _tool_entity_id(action, state)
    if tool_id and "$tool" in expanded.get("entities", {}):
        expanded["entities"][tool_id] = expanded["entities"].pop("$tool")
    return expanded


def _replace_placeholders(value: object, action: Action, state: GameState) -> object:
    tool_entity = _tool_entity(action, state)
    tool_entity_id = _tool_entity_id(action, state)
    target = state.entities.get(str(action.get("target_id") or ""), {})

    def _leaf(v: object) -> object:
        if v == "$target":
            return action.get("target_id") or "$target"
        if v == "$tool":
            return tool_entity_id or action.get("tool_id") or "$tool"
        if v == "$tool_debris":
            return f"{tool_entity_id or str(action.get('tool_id') or 'tool')}_debris"
        if v == "$tool_contents":
            return list(tool_entity.get("contents", []))
        if isinstance(v, str):
            return (
                v.replace("$target_name", str(target.get("name") or action.get("target") or "目标"))
                .replace("$tool_name", str(tool_entity.get("name") or action.get("tool") or "工具"))
            )
        return v

    return traverse_replace(value, _leaf)


def _tool_entity_id(action: Action, state: GameState) -> str:
    tool_id = str(action.get("tool_id") or "")
    if tool_id in state.entities:
        return tool_id
    for entity_id, entity in state.entities.items():
        names = [
            str(entity.get("item_id") or ""),
            str(entity.get("name") or ""),
            *[str(alias) for alias in entity.get("aliases", [])],
        ]
        if tool_id in names:
            return entity_id
    return ""


def _tool_entity(action: Action, state: GameState) -> dict[str, object]:
    tool_id = _tool_entity_id(action, state)
    if tool_id:
        return state.entities.get(tool_id, {})
    return {}
