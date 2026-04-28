from __future__ import annotations

from diceflow.core.intent import action_family, normalize_action
from diceflow.core.implied_entity import resolve_implied_entity
from diceflow.core.models import Action
from diceflow.core.state import GameState
from diceflow.scripting.resolver import get_allowed_actions, resolve_action_spec
from diceflow.scripting.scene_rules import validate_scene_rules


TARGET_REQUIRED_FAMILIES = {"attack", "open", "use", "throw", "talk", "take"}


def validate(action: Action, state: GameState) -> dict[str, str | bool]:
    """Validate and normalize an action against game state.

    The input *action* is never mutated.  A fresh normalized copy is placed
    in ``result["_normalized_action"]`` for the caller.

    When an implied entity is spawned it is applied to *state* directly so
    that action-spec resolution sees it.  The caller is notified via
    ``_implied_spawn_applied`` in the result dict.
    """
    action = normalize_action(action, state)
    implied_spawn_applied = False

    if action.get("target") and not action.get("target_id"):
        target_id, implied_spawn = resolve_implied_entity(action, state)
        if target_id:
            action["target_id"] = target_id
            if implied_spawn:
                state.apply_changes(implied_spawn)
                implied_spawn_applied = True

    intent_family = action_family(action)
    action_spec = resolve_action_spec(action, state)
    target = action.get("target")
    target_id = action.get("target_id") or (state.find_entity_id(str(target)) if target else None)
    if intent_family in TARGET_REQUIRED_FAMILIES and target and not target_id:
        return {"valid": False, "reason": f"目标不存在或不明确：{target}", "_normalized_action": action}
    if not action_spec.get("outcomes"):
        return {"valid": False, "reason": f"暂不支持行动类型：{intent_family}", "_normalized_action": action}
    action_scope = str(action_spec.get("scope") or "")
    is_scene_action = action_scope == "scene"
    is_generic_action = action_scope == "generic_rule"

    if _requires_target(intent_family, state) and not target_id:
        return {"valid": False, "reason": f"目标不存在或不明确：{target or '未提供'}", "_normalized_action": action}

    if target_id and not is_scene_action:
        action["target_id"] = target_id
        if not state.is_interactable_entity(target_id):
            return {"valid": False, "reason": f"目标当前不可交互：{target or target_id}", "_normalized_action": action}
        entity = state.entities[target_id]
        allowed_actions = get_allowed_actions(entity)
        if not is_generic_action and intent_family not in allowed_actions:
            return {
                "valid": False,
                "reason": f"{entity.get('name', target_id)}不能执行该行动：{intent_family}",
                "_normalized_action": action,
            }
        if not is_generic_action:
            state_result = _validate_entity_action_state(intent_family, entity)
            if not state_result["valid"]:
                state_result["_normalized_action"] = action
                return state_result
    elif target_id:
        action["target_id"] = target_id

    if intent_family == "attack" and target_id:
        if not state.entities[target_id].get("alive", True):
            return {"valid": False, "reason": "目标已经失去威胁。", "_normalized_action": action}

    required_tools = action_spec.get("required_tools", [])
    if intent_family == "use" and required_tools:
        tool_id = action.get("tool_id")
        if not _tool_matches_required(tool_id, required_tools, state):
            return {"valid": False, "reason": f"该行动需要使用：{'、'.join(required_tools)}。", "_normalized_action": action}

    for tool in required_tools:
        if not _has_required_tool(tool, state):
            return {"valid": False, "reason": f"你没有可用的{tool}。", "_normalized_action": action}

    result = validate_scene_rules(action, state)
    result["_normalized_action"] = action
    if implied_spawn_applied:
        result["_implied_spawn_applied"] = True
    return result


def _validate_entity_action_state(intent_family: str, entity: dict[str, object]) -> dict[str, str | bool]:
    entity_name = str(entity.get("name") or "目标")

    if entity.get("destroyed") and intent_family not in {"inspect"}:
        return {"valid": False, "reason": f"{entity_name}已经被破坏，不能再这样做。"}
    if intent_family == "open" and entity.get("opened"):
        return {"valid": False, "reason": f"{entity_name}已经打开。"}
    if intent_family == "take" and entity.get("looted"):
        return {"valid": False, "reason": f"{entity_name}已经被拿走。"}

    return {"valid": True, "reason": ""}


def _requires_target(intent_family: str, state: GameState) -> bool:
    if intent_family in state.script.get("scene_actions", {}):
        return False
    return intent_family in TARGET_REQUIRED_FAMILIES or any(
        state.is_interactable_entity(entity_id) and intent_family in get_allowed_actions(entity)
        for entity_id, entity in state.entities.items()
    )


def _has_required_tool(tool: str, state: GameState) -> bool:
    if tool in state.player.get("inventory", []):
        return True
    tool_entity_id = state.find_entity_id(tool)
    return bool(tool_entity_id and state.is_interactable_entity(tool_entity_id))


def _tool_matches_required(tool_id: object, required_tools: list[str], state: GameState) -> bool:
    tool_text = str(tool_id or "")
    if tool_text in required_tools:
        return True
    for required_tool in required_tools:
        if state.find_inventory_item(required_tool) == tool_text:
            return True
        if state.find_entity_id(required_tool) == tool_text:
            return True
    return False
