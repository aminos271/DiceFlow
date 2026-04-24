from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action, StateChanges
from diceflow.core.runtime_content import sanitize_add_entity_op
from diceflow.core.runtime_patch import normalize_runtime_script_patch
from diceflow.core.state import GameState


LOGGER = logging.getLogger(__name__)
WORLD_SOURCE = "dynamic_world"
TRANSITION_FAMILIES = {"move", "inspect", "interact", "unknown"}
TRANSITION_TERMS = {
    "进入",
    "进去",
    "内部",
    "里面",
    "门后",
    "通道",
    "探索",
    "前进",
    "穿过",
    "走进",
}


def dynamic_world_phase(
    action: Action,
    validation: dict[str, Any],
    state: GameState,
    llm: Any | None = None,
) -> StateChanges:
    if validation.get("valid") or state.flags.get("game_over"):
        return {}
    if not _has_world_contract(state) or not _looks_like_transition(action):
        return {}
    if not _has_transition_opening(state):
        return {}

    try:
        raw_patch = _generate_world_patch(action, validation, state, llm)
        patch = validate_world_patch(raw_patch, state)
    except Exception as exc:
        LOGGER.warning("dynamic world generation failed: %s", exc)
        return {}
    if not patch:
        return {}
    return {
        "runtime_script_patch": patch,
        "flags": {"dynamic_world_used": True},
        "events": _events_from_patch(patch),
    }


def validate_world_patch(patch: object, state: GameState) -> dict[str, Any] | None:
    world = _world_contract(state)
    try:
        normalized = normalize_runtime_script_patch(patch)  # type: ignore[arg-type]
        allowed_entity_types = set(str(item) for item in world["allowed_entity_types"])
        max_dc = int(world["max_runtime_dc"])
        max_entities = int(world["max_new_entities_per_transition"])
        existing_ids = set(state.script.get("entities", {})) | set(state.entities)
        safe_ops: list[dict[str, Any]] = []
        scene_count = 0
        entity_count = 0

        for op in normalized["ops"]:
            op_name = str(op.get("op") or "")
            if op_name == "set_scene":
                scene_count += 1
                safe_ops.append(deepcopy(op))
            elif op_name == "add_scene_action":
                _validate_scene_action_op(op, max_dc)
                safe_ops.append(deepcopy(op))
            elif op_name == "set_flag":
                key = str(op.get("key") or "")
                if not (key.startswith("generated.") or key.startswith("runtime.")):
                    raise ValueError(f"flag outside runtime/generated namespace: {key}")
                safe_ops.append(deepcopy(op))
            elif op_name == "add_entity":
                entity_count += 1
                entity_id = str(op.get("id") or "")
                if entity_id in existing_ids:
                    raise ValueError(f"entity id already exists: {entity_id}")
                if not entity_id.startswith("dyn_"):
                    entity_id = f"dyn_{entity_id}"
                if entity_id in existing_ids:
                    raise ValueError(f"entity id already exists after prefixing: {entity_id}")
                safe_entity_op = sanitize_add_entity_op({**op, "id": entity_id}, allowed_entity_types, max_dc)
                safe_ops.append(safe_entity_op)
                existing_ids.add(entity_id)
            else:
                raise ValueError(f"unsupported dynamic world op: {op_name}")

        if scene_count != 1:
            raise ValueError("dynamic world patch requires exactly one set_scene op")
        if entity_count > max_entities:
            raise ValueError(f"too many generated entities: {entity_count}")
        return {
            "id": str(normalized.get("id") or f"dynamic_world_{state.turn_id}"),
            "source": WORLD_SOURCE,
            "turn_id": state.turn_id,
            "ops": safe_ops,
        }
    except Exception as exc:
        LOGGER.warning("discarding invalid dynamic world patch: %s", exc)
        return None


def _generate_world_patch(
    action: Action,
    validation: dict[str, Any],
    state: GameState,
    llm: Any | None,
) -> object:
    if llm and hasattr(llm, "generate_dynamic_world"):
        return llm.generate_dynamic_world(_world_contract(state), action, validation, state)
    return _fallback_world_patch(action, state)


def _fallback_world_patch(action: Action, state: GameState) -> dict[str, Any]:
    scene_id = f"dyn_scene_{state.turn_id}"
    return {
        "id": f"dynamic_world_turn_{state.turn_id}",
        "source": WORLD_SOURCE,
        "turn_id": state.turn_id,
        "ops": [
            {
                "op": "set_scene",
                "scene": {
                    "id": scene_id,
                    "name": "未知通道",
                    "description": "你离开原本的入口，进入一段尚未记录在剧本中的幽暗空间。",
                },
            },
            {"op": "set_flag", "key": "runtime.current_scene_id", "value": scene_id},
            {"op": "set_flag", "key": f"generated.{scene_id}", "value": True},
            {
                "op": "add_scene_action",
                "action": "inspect",
                "spec": {
                    "dc": min(9, int(_world_contract(state)["max_runtime_dc"])),
                    "outcomes": {
                        "success": {
                            "events": ["你观察这个新区域，确认这里还有更多细节值得探索。"]
                        },
                        "fail": {
                            "events": ["光线和回声干扰了你的判断，你暂时没有看出更多线索。"]
                        },
                    },
                },
            },
        ],
    }


def _has_world_contract(state: GameState) -> bool:
    return isinstance(state.script.get("world"), dict)


def _world_contract(state: GameState) -> dict[str, Any]:
    world = state.script.get("world", {})
    if not isinstance(world, dict):
        world = {}
    return {
        "premise": str(world.get("premise") or state.script.get("title") or ""),
        "tone": str(world.get("tone") or ""),
        "allowed_scene_types": list(world.get("allowed_scene_types") or ["corridor", "chamber"]),
        "allowed_entity_types": list(world.get("allowed_entity_types") or ["pickup", "container", "npc", "obstacle"]),
        "forbidden": list(world.get("forbidden") or []),
        "max_runtime_dc": int(world.get("max_runtime_dc") or 14),
        "max_new_entities_per_transition": int(world.get("max_new_entities_per_transition") or 4),
    }


def _looks_like_transition(action: Action) -> bool:
    family = action_family(action)
    text = f"{action.get('target', '')} {action.get('method_text') or action.get('method') or ''}"
    return family in TRANSITION_FAMILIES and any(term in text for term in TRANSITION_TERMS)


def _has_transition_opening(state: GameState) -> bool:
    if state.flags.get("door_open") or state.flags.get("scene_is_open"):
        return True
    for entity in state.get_visible_entities().values():
        if entity.get("opened") and ("door" in entity.get("tags", []) or entity.get("type") == "door"):
            return True
    return False


def _validate_scene_action_op(op: dict[str, Any], max_dc: int) -> None:
    action = str(op.get("action") or "")
    spec = op.get("spec")
    if action not in {"move", "inspect", "interact", "wait", "flee"}:
        raise ValueError(f"scene action is not allowed: {action}")
    if not isinstance(spec, dict):
        raise ValueError("scene action spec must be a dict")
    dc = spec.get("dc")
    if not isinstance(dc, int) or dc < 5 or dc > max_dc:
        raise ValueError(f"scene action dc must be between 5 and {max_dc}")
    outcomes = spec.get("outcomes")
    if not isinstance(outcomes, dict) or not outcomes:
        raise ValueError("scene action outcomes must be a non-empty dict")
    for changes in outcomes.values():
        if not isinstance(changes, dict):
            raise ValueError("scene action outcome changes must be dicts")
        if "player" in changes:
            raise ValueError("dynamic world scene actions cannot directly modify player")


def _events_from_patch(patch: dict[str, Any]) -> list[str]:
    events: list[str] = []
    for op in patch.get("ops", []):
        if op.get("op") == "set_scene":
            scene = op.get("scene", {})
            events.append(f"你进入{scene.get('name', '新的区域')}。")
            break
    return events or ["你离开原本的剧本边界，进入新的区域。"]
