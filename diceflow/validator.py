from __future__ import annotations

from diceflow.models import Action
from diceflow.script import get_action_spec, get_allowed_actions
from diceflow.script_rules import validate_scene_rules
from diceflow.state import GameState


TARGET_REQUIRED_TYPES = {"attack", "open", "burn", "talk"}


def validate(action: Action, state: GameState) -> dict[str, str | bool]:
    action_type = str(action.get("type") or "unknown")
    if not _is_supported_action(action_type, state):
        return {"valid": False, "reason": f"暂不支持行动类型：{action_type}"}

    target = action.get("target")
    target_id = state.find_entity_id(str(target)) if target else None
    if _requires_target(action_type, state) and not target_id:
        return {"valid": False, "reason": f"目标不存在或不明确：{target or '未提供'}"}

    if target_id:
        action["target_id"] = target_id
        entity = state.entities[target_id]
        allowed_actions = get_allowed_actions(entity)
        if action_type not in allowed_actions:
            return {
                "valid": False,
                "reason": f"{entity.get('name', target_id)}不能执行该行动：{action_type}",
            }

    action_spec = get_action_spec(action, state)

    if action_type == "attack":
        if not state.entities[target_id].get("alive", True):
            return {"valid": False, "reason": "目标已经失去威胁。"}

    for tool in action_spec.get("required_tools", []):
        if tool not in state.player.get("inventory", []):
            return {"valid": False, "reason": f"你没有可用的{tool}。"}

    return validate_scene_rules(action, state)


def _is_supported_action(action_type: str, state: GameState) -> bool:
    if action_type in state.script.get("scene_actions", {}):
        return True
    return any(action_type in get_allowed_actions(entity) for entity in state.entities.values())


def _requires_target(action_type: str, state: GameState) -> bool:
    if action_type in state.script.get("scene_actions", {}):
        return False
    return action_type in TARGET_REQUIRED_TYPES or any(
        action_type in get_allowed_actions(entity) for entity in state.entities.values()
    )
