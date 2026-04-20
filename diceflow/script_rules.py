from __future__ import annotations

from diceflow.intent import action_family
from diceflow.models import Action
from diceflow.state import GameState


def validate_scene_rules(action: Action, state: GameState) -> dict[str, str | bool]:
    action_type = action_family(action)
    target_id = action.get("target_id")

    if action_type == "open" and target_id == "left_door":
        if state.entities.get("guard_1", {}).get("alive", False):
            return {
                "valid": False,
                "reason": "守卫仍挡在门前，你必须先处理守卫或摆脱他的压制。",
            }

    return {"valid": True, "reason": ""}


def get_dc_modifier(action: Action, state: GameState) -> int:
    action_type = action_family(action)
    target_id = action.get("target_id")
    modifier = 0

    if action_type == "open" and target_id == "left_door":
        if state.entities["left_door"].get("weakened"):
            modifier -= 3

    if action_type == "attack" and target_id == "guard_1":
        if not state.entities["guard_1"].get("hostile", True):
            modifier -= 2

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
