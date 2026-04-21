from __future__ import annotations

from diceflow.intent import action_family
from diceflow.models import Action
from diceflow.state import GameState


def validate_scene_rules(action: Action, state: GameState) -> dict[str, str | bool]:
    for rule in state.script.get("action_rules", []):
        if _matches_when(rule.get("when", {}), action, state):
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
        if _matches_when(rule.get("when", {}), action, state):
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


def _matches_when(when: object, action: Action, state: GameState) -> bool:
    if not isinstance(when, dict):
        return False

    action_type = action_family(action)
    target_id = str(action.get("target_id") or "")
    target = state.entities.get(target_id, {})

    if "intent_family" in when and not _matches_value(action_type, when["intent_family"]):
        return False
    if "target_id" in when and not _matches_value(target_id, when["target_id"]):
        return False
    if "target_type" in when and not _matches_value(str(target.get("type") or ""), when["target_type"]):
        return False
    if "target" in when and not _matches_object(target, when["target"]):
        return False
    if "flags" in when and not _matches_object(state.flags, when["flags"]):
        return False

    entities = when.get("entities", {})
    if isinstance(entities, dict):
        for entity_id, expected in entities.items():
            if not _matches_object(state.entities.get(str(entity_id), {}), expected):
                return False

    return True


def _matches_value(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def _matches_object(actual: dict[str, object], expected: object) -> bool:
    if not isinstance(expected, dict):
        return False
    for key, expected_value in expected.items():
        if actual.get(str(key)) != expected_value:
            return False
    return True
