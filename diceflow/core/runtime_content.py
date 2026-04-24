from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.runtime_patch import normalize_runtime_script_patch
from diceflow.core.state import GameState
from diceflow.scripting.scene_rules import matches_when


LOGGER = logging.getLogger(__name__)
RUNTIME_CONTENT_SOURCE = "runtime_content_generator"
ALLOWED_OPS = {"add_entity", "set_flag"}
DEFAULT_MAX_DC = 15
MAX_HP = 20
MAX_DELTA_ABS = 10


def runtime_content_phase(
    action: Action,
    check: CheckResult,
    action_changes: StateChanges,
    state: GameState,
    llm: Any | None = None,
) -> StateChanges:
    del action_changes

    if not llm or state.flags.get("game_over"):
        return {}

    for hook in state.script.get("runtime_generation_hooks", []):
        if not _matches_hook(hook, action, check, state):
            continue
        try:
            raw_patch = _generate_patch(llm, hook, action, check, state)
            patch = validate_runtime_patch(raw_patch, hook, state)
        except Exception as exc:
            LOGGER.warning("runtime content generation failed for hook %s: %s", hook.get("id"), exc)
            return {}
        if patch:
            return {"runtime_script_patch": patch}
    return {}


def validate_runtime_patch(patch: object, hook: dict[str, Any], state: GameState) -> dict[str, Any] | None:
    """Validate and sanitize an LLM-produced runtime content patch.

    Invalid patches are dropped. The game continues without generated content.
    """
    try:
        normalized = normalize_runtime_script_patch(patch)  # type: ignore[arg-type]
        allowed_entity_types = set(str(item) for item in hook.get("allowed_entity_types", []))
        max_dc = int(hook.get("max_dc") or DEFAULT_MAX_DC)
        existing_ids = set(state.script.get("entities", {})) | set(state.entities)
        safe_ops: list[dict[str, Any]] = []

        for op in normalized["ops"]:
            op_name = str(op.get("op") or "")
            if op_name not in ALLOWED_OPS:
                raise ValueError(f"unsupported runtime content op: {op_name}")
            if op_name == "add_entity":
                entity_id = str(op.get("id") or "")
                if entity_id in existing_ids:
                    raise ValueError(f"entity id already exists: {entity_id}")
                if not entity_id.startswith("dyn_"):
                    entity_id = f"dyn_{entity_id}"
                if entity_id in existing_ids:
                    raise ValueError(f"entity id already exists after prefixing: {entity_id}")
                entity = _sanitize_entity(op.get("entity"), allowed_entity_types, max_dc)
                safe_ops.append({"op": "add_entity", "id": entity_id, "entity": entity})
                existing_ids.add(entity_id)
            elif op_name == "set_flag":
                key = str(op.get("key") or "")
                if not key.startswith("generated."):
                    raise ValueError(f"runtime content flag must start with generated.: {key}")
                safe_ops.append({"op": "set_flag", "key": key, "value": deepcopy(op.get("value"))})

        if not safe_ops:
            return None

        marker_key = _generated_flag_key(hook)
        if not any(op.get("op") == "set_flag" and op.get("key") == marker_key for op in safe_ops):
            safe_ops.append({"op": "set_flag", "key": marker_key, "value": True})

        return {
            "id": str(normalized.get("id") or f"runtime_content_{state.turn_id}"),
            "source": RUNTIME_CONTENT_SOURCE,
            "turn_id": state.turn_id,
            "ops": safe_ops,
        }
    except Exception as exc:
        LOGGER.warning("discarding invalid runtime content patch for hook %s: %s", hook.get("id"), exc)
        return None


def _matches_hook(hook: object, action: Action, check: CheckResult, state: GameState) -> bool:
    if not isinstance(hook, dict):
        return False
    hook_id = str(hook.get("id") or "")
    if not hook_id or state.flags.get(_generated_flag_key(hook)):
        return False
    if str(check.get("result") or "") not in {"success", "critical_success"}:
        return False
    when = hook.get("when", {})
    if not isinstance(when, dict):
        return False
    result_when = when.get("result")
    if result_when is not None and not _matches_value(str(check.get("result") or ""), result_when):
        return False
    base_when = {key: value for key, value in when.items() if key != "result"}
    return matches_when(base_when, action, state)


def _generate_patch(
    llm: Any,
    hook: dict[str, Any],
    action: Action,
    check: CheckResult,
    state: GameState,
) -> object:
    if hasattr(llm, "generate_runtime_content"):
        return llm.generate_runtime_content(hook, action, check, state)
    return None


def _sanitize_entity(raw_entity: object, allowed_entity_types: set[str], max_dc: int) -> dict[str, Any]:
    if not isinstance(raw_entity, dict):
        raise ValueError("entity must be a dict")
    entity = deepcopy(raw_entity)
    entity_type = str(entity.get("type") or "")
    if entity_type not in allowed_entity_types:
        raise ValueError(f"entity type is not allowed: {entity_type}")
    if int(entity.get("hp", 0) or 0) > MAX_HP:
        raise ValueError("entity hp exceeds runtime content limit")
    if int(entity.get("max_hp", 0) or 0) > MAX_HP:
        raise ValueError("entity max_hp exceeds runtime content limit")

    metadata = entity.get("metadata", {})
    if metadata is None:
        metadata = {}
        entity["metadata"] = metadata
    if not isinstance(metadata, dict):
        raise ValueError("entity metadata must be a dict")
    actions = metadata.get("actions", {})
    if actions is None:
        actions = {}
        metadata["actions"] = actions
    if not isinstance(actions, dict):
        raise ValueError("entity metadata.actions must be a dict")

    for action_type, action_spec in actions.items():
        if not isinstance(action_type, str) or not isinstance(action_spec, dict):
            raise ValueError("entity actions must be a dict of action specs")
        _sanitize_action_spec(action_spec, max_dc)

    allowed_actions = metadata.get("allowed_actions")
    if allowed_actions is not None:
        if not isinstance(allowed_actions, list) or not all(isinstance(item, str) for item in allowed_actions):
            raise ValueError("metadata.allowed_actions must be a string list")
        for allowed_action in allowed_actions:
            if allowed_action not in actions:
                raise ValueError(f"allowed action has no action spec: {allowed_action}")

    return entity


def _sanitize_action_spec(action_spec: dict[str, Any], max_dc: int) -> None:
    dc = action_spec.get("dc")
    if not isinstance(dc, int) or dc < 5 or dc > max_dc:
        raise ValueError(f"action dc must be between 5 and {max_dc}")
    outcomes = action_spec.get("outcomes")
    if not isinstance(outcomes, dict) or not outcomes:
        raise ValueError("action outcomes must be a non-empty dict")
    for changes in outcomes.values():
        _validate_runtime_changes(changes)


def _validate_runtime_changes(changes: object) -> None:
    if not isinstance(changes, dict):
        raise ValueError("outcome changes must be a dict")
    if "player" in changes:
        raise ValueError("runtime content cannot directly modify player")
    if "runtime_script_patch" in changes:
        raise ValueError("runtime content actions cannot nest runtime patches")
    for child in ("entities", "set_entity_states"):
        value = changes.get(child)
        if isinstance(value, dict):
            for entity_changes in value.values():
                _validate_entity_changes(entity_changes)


def _validate_entity_changes(changes: object) -> None:
    if not isinstance(changes, dict):
        return
    for key, value in changes.items():
        if key.endswith("_delta"):
            if not isinstance(value, int) or abs(value) > MAX_DELTA_ABS:
                raise ValueError(f"entity delta out of range: {key}")


def _generated_flag_key(hook: dict[str, Any]) -> str:
    return f"generated.{hook.get('id')}"


def _matches_value(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected
