from __future__ import annotations

from diceflow.core.intent import action_family
from diceflow.core.matching import matches_all_tags, matches_any_tag, matches_object, matches_value
from diceflow.core.models import Action
from diceflow.core.state import GameState


def validate_scene_rules(action: Action, state: GameState) -> dict[str, str | bool]:
    for rule in state.script.get("action_rules", []):
        if matches_when(rule.get("when", {}), action, state):
            return {
                "valid": bool(rule.get("valid", True)),
                "reason": str(rule.get("reason", "")),
            }

    return {"valid": True, "reason": ""}


def get_dc_modifier(action: Action, state: GameState) -> int:
    action_type = action_family(action)
    target_id = action.get("target_id")
    modifier = 0

    for rule in state.script.get("dc_modifiers", []):
        if matches_when(rule.get("when", {}), action, state):
            modifier += int(rule.get("modifier", 0))

    modifier += _approach_dc_modifier(action_type, action.get("approach_tags", []))
    return modifier


def _approach_dc_modifier(action_type: str, approach_tags: object) -> int:
    tags = set(approach_tags if isinstance(approach_tags, list) else [])
    modifier = 0

    if "careful" in tags:
        modifier -= 1
    if "forceful" in tags and action_type in {"attack", "open"}:
        modifier -= 1
    if "quick" in tags:
        modifier += 1

    return modifier


def matches_when(when: object, action: Action, state: GameState) -> bool:
    if not isinstance(when, dict):
        return False

    action_type = action_family(action)
    target_id = str(action.get("target_id") or "")
    target = state.entities.get(target_id, {})

    if "intent_family" in when and not matches_value(action_type, when["intent_family"]):
        return False
    if "target_id" in when and not matches_value(target_id, when["target_id"]):
        return False
    if "target_type" in when and not matches_value(str(target.get("type") or ""), when["target_type"]):
        return False
    if "target" in when and not matches_object(target, when["target"]):
        return False
    if "flags" in when and not matches_object(state.flags, when["flags"]):
        return False

    entities = when.get("entities", {})
    if isinstance(entities, dict):
        for entity_id, expected in entities.items():
            if not matches_object(state.entities.get(str(entity_id), {}), expected):
                return False

    target_tags = target.get("tags", [])
    if "target_tags" in when and not matches_all_tags(target_tags, when["target_tags"]):
        return False
    if "any_target_tags" in when and not matches_any_tag(target_tags, when["any_target_tags"]):
        return False

    tool = _resolve_tool_entity(action, state)
    tool_tags = tool.get("tags", [])
    if "tool_tags" in when and not matches_all_tags(tool_tags, when["tool_tags"]):
        return False
    if "any_tool_tags" in when and not matches_any_tag(tool_tags, when["any_tool_tags"]):
        return False

    return True


def _resolve_tool_entity(action: Action, state: GameState) -> dict[str, object]:
    tool_id = str(action.get("tool_id") or "")
    if not tool_id:
        return {}
    if tool_id in state.entities:
        return state.entities[tool_id]
    for entity in state.entities.values():
        names = [
            str(entity.get("item_id") or ""),
            str(entity.get("name") or ""),
            *[str(alias) for alias in entity.get("aliases", [])],
        ]
        if tool_id in names:
            return entity
    return {}


