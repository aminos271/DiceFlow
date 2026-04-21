from __future__ import annotations

from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action


Script = dict[str, Any]


def get_entity_action(script: Script, entity: dict[str, Any], action_type: str) -> dict[str, Any]:
    return entity.get("metadata", {}).get("actions", {}).get(action_type, {})


def get_allowed_actions(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if "allowed_actions" in metadata:
        return list(metadata["allowed_actions"])
    return list(metadata.get("actions", {}).keys())


def resolve_action_spec(action: Action, state: Any) -> dict[str, Any]:
    action_type = action_family(action)
    target_id = str(action.get("target_id") or "")
    tool_id = str(action.get("tool_id") or "")
    scope = "scene"
    action_spec: dict[str, Any] = {}

    if target_id and target_id in state.entities:
        entity = state.entities[target_id]
        entity_action = get_entity_action(state.script, entity, action_type)
        if entity_action:
            scope = "entity"
            action_spec = entity_action
    if not action_spec:
        action_spec = state.script.get("scene_actions", {}).get(action_type, {})

    return {
        **action_spec,
        "intent_family": action_type,
        "scope": scope,
        "target_id": target_id,
        "tool_id": tool_id,
    }


def get_action_spec(action: Action, state: Any) -> dict[str, Any]:
    return resolve_action_spec(action, state)

