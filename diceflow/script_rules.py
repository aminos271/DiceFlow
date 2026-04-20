from __future__ import annotations

from diceflow.models import Action
from diceflow.state import GameState


def validate_scene_rules(action: Action, state: GameState) -> dict[str, str | bool]:
    action_type = str(action.get("intent_family") or action.get("type") or "unknown")
    target_id = action.get("target_id")

    if action_type == "open" and target_id == "left_door":
        if state.entities.get("guard_1", {}).get("alive", False):
            return {
                "valid": False,
                "reason": "守卫仍挡在门前，你必须先处理守卫或摆脱他的压制。",
            }

    return {"valid": True, "reason": ""}


def get_dc_modifier(action: Action, state: GameState) -> int:
    action_type = str(action.get("intent_family") or action.get("type") or "unknown")
    target_id = action.get("target_id")
    modifier = 0

    if action_type == "open" and target_id == "left_door":
        if state.entities["left_door"].get("weakened"):
            modifier -= 3

    if action_type == "attack" and target_id == "guard_1":
        if not state.entities["guard_1"].get("hostile", True):
            modifier -= 2

    return modifier
