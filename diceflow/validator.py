from __future__ import annotations

from diceflow.intent import action_family, normalize_action
from diceflow.models import Action
from diceflow.script import get_allowed_actions, resolve_action_spec
from diceflow.script_rules import validate_scene_rules
from diceflow.state import GameState


TARGET_REQUIRED_FAMILIES = {"attack", "open", "use", "talk"}


def validate(action: Action, state: GameState) -> dict[str, str | bool]:
    action.update(normalize_action(action, state))
    intent_family = action_family(action)
    if not _is_supported_action(intent_family, state):
        return {"valid": False, "reason": f"暂不支持行动类型：{intent_family}"}

    target = action.get("target")
    target_id = action.get("target_id") or (state.find_entity_id(str(target)) if target else None)
    is_scene_action = intent_family in state.script.get("scene_actions", {})
    if _requires_target(intent_family, state) and not target_id:
        return {"valid": False, "reason": f"目标不存在或不明确：{target or '未提供'}"}

    if target_id and not is_scene_action:
        action["target_id"] = target_id
        entity = state.entities[target_id]
        allowed_actions = get_allowed_actions(entity)
        if intent_family not in allowed_actions:
            return {
                "valid": False,
                "reason": f"{entity.get('name', target_id)}不能执行该行动：{intent_family}",
            }
    elif target_id:
        action["target_id"] = target_id

    action_spec = resolve_action_spec(action, state)

    if intent_family == "attack":
        if not state.entities[target_id].get("alive", True):
            return {"valid": False, "reason": "目标已经失去威胁。"}

    required_tools = action_spec.get("required_tools", [])
    if intent_family == "use" and required_tools:
        tool_id = action.get("tool_id")
        if tool_id not in required_tools:
            return {"valid": False, "reason": f"该行动需要使用：{'、'.join(required_tools)}。"}

    for tool in required_tools:
        if tool not in state.player.get("inventory", []):
            return {"valid": False, "reason": f"你没有可用的{tool}。"}

    return validate_scene_rules(action, state)


def _is_supported_action(intent_family: str, state: GameState) -> bool:
    if intent_family in state.script.get("scene_actions", {}):
        return True
    return any(intent_family in get_allowed_actions(entity) for entity in state.entities.values())


def _requires_target(intent_family: str, state: GameState) -> bool:
    if intent_family in state.script.get("scene_actions", {}):
        return False
    return intent_family in TARGET_REQUIRED_FAMILIES or any(
        intent_family in get_allowed_actions(entity) for entity in state.entities.values()
    )
