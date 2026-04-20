from __future__ import annotations

from diceflow.models import Action
from diceflow.state import GameState


TARGET_REQUIRED_TYPES = {"attack", "open", "burn", "talk"}
TARGET_OPTIONAL_TYPES = {"inspect", "wait", "flee", "unknown"}
SUPPORTED_TYPES = TARGET_REQUIRED_TYPES | TARGET_OPTIONAL_TYPES


def validate(action: Action, state: GameState) -> dict[str, str | bool]:
    action_type = str(action.get("type") or "unknown")
    if action_type not in SUPPORTED_TYPES:
        return {"valid": False, "reason": f"暂不支持行动类型：{action_type}"}

    target = action.get("target")
    target_id = state.find_entity_id(str(target)) if target else None
    if action_type in TARGET_REQUIRED_TYPES and not target_id:
        return {"valid": False, "reason": f"目标不存在或不明确：{target or '未提供'}"}

    if target_id:
        action["target_id"] = target_id
        entity = state.entities[target_id]
        allowed_actions = entity.get("metadata", {}).get("allowed_actions", [])
        if action_type not in allowed_actions:
            return {
                "valid": False,
                "reason": f"{entity.get('name', target_id)}不能执行该行动：{action_type}",
            }

    if action_type == "attack":
        if not state.entities[target_id].get("alive", True):
            return {"valid": False, "reason": "目标已经失去威胁。"}

    if action_type == "burn" and "火把" not in state.player.get("inventory", []):
        return {"valid": False, "reason": "你没有可用的火把。"}

    return {"valid": True, "reason": ""}
