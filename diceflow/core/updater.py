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
        return _expand_placeholders(outcomes[result], action, state)
    if "fail" in outcomes:
        return _expand_placeholders(outcomes["fail"], action, state)

    return {
        "player": {"hp_delta": -1},
        "events": [str(state.script.get("default_no_outcome_event", "行动没有产生明确结果，但局势继续推进。"))],
    }


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
    if value == "$target":
        return action.get("target_id") or "$target"
    if value == "$tool":
        return _tool_entity_id(action, state) or action.get("tool_id") or "$tool"
    if value == "$tool_debris":
        tool_id = _tool_entity_id(action, state) or str(action.get("tool_id") or "tool")
        return f"{tool_id}_debris"
    if value == "$tool_contents":
        return list(_tool_entity(action, state).get("contents", []))
    if isinstance(value, str):
        target = state.entities.get(str(action.get("target_id") or ""), {})
        tool = _tool_entity(action, state)
        return (
            value.replace("$target_name", str(target.get("name") or action.get("target") or "目标"))
            .replace("$tool_name", str(tool.get("name") or action.get("tool") or "工具"))
        )
    if isinstance(value, list):
        return [_replace_placeholders(item, action, state) for item in value]
    if isinstance(value, dict):
        replaced = {}
        for key, item in value.items():
            replaced_key = str(_replace_placeholders(key, action, state))
            if replaced_key == "spawn_entities":
                replaced[replaced_key] = {
                    str(_replace_placeholders(entity_id, action, state)): _replace_spawn_entity(entity, action, state)
                    for entity_id, entity in item.items()
                }
            else:
                replaced[replaced_key] = _replace_placeholders(item, action, state)
        return replaced
    return value


def _replace_spawn_entity(value: object, action: Action, state: GameState) -> object:
    if isinstance(value, dict):
        return {
            str(_replace_placeholders(key, action, state)): (
                item if key == "metadata" else _replace_spawn_entity(item, action, state)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_spawn_entity(item, action, state) for item in value]
    return _replace_placeholders(value, action, state)


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
