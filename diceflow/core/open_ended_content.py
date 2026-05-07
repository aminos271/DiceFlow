from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from diceflow.core.dynamic_world import _world_contract
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.runtime_content import sanitize_add_entity_op
from diceflow.core.runtime_patch import normalize_runtime_script_patch
from diceflow.core.state import GameState

LOGGER = logging.getLogger(__name__)
OPEN_ENDED_SOURCE = "open_ended_content"
OPEN_ENDED_INTENT_KINDS = frozenset({"social", "discover", "improvised", "create_environment"})
# Intent kinds that can produce entities without LLM via dynamic_entity_templates
NO_LLM_SPAWN_INTENT_KINDS = frozenset({"discover", "create_environment"})
OPEN_ENDED_ALLOWED_OPS = frozenset({"add_entity", "set_flag"})
SOCIAL_HINT_KEYWORDS = frozenset({"招募", "同伴", "队友", "结伴", "推荐", "打听", "消息", "线索", "活计", "活儿"})
DISCOVER_HINT_KEYWORDS = frozenset({"找", "寻找", "搜索", "搜查", "查看", "观察", "线索", "有没有", "可疑"})
ENVIRONMENT_HINT_KEYWORDS = frozenset({"堆", "搬", "摆", "布置", "制造", "搭", "堵", "路障", "陷阱"})

# Minimal fallback for no-LLM dynamic entity spawning when no script template exists.
FALLBACK_DYNAMIC_SPAWN: dict[str, Any] = {"name": "临时发现", "type": "clue", "tags": ["dynamic"]}


def open_ended_content_phase(
    action: Action,
    check: CheckResult,
    adjudicator_changes: StateChanges,
    state: GameState,
    llm: Any | None = None,
) -> StateChanges:
    """Generate roll-quality-dependent content for open-ended turns.

    Triggers when:
    - Game is not over
    - Result is not impossible
    - Intent kind can be inferred as social / discover / improvised / create_environment
    - Script has an explicit world contract for the LLM path
    """
    del adjudicator_changes

    if state.flags.get("game_over"):
        return {}
    result = str(check.get("result") or "")
    if result == "impossible":
        return {}

    intent_kind = _infer_open_ended_intent_kind(action, check)
    if intent_kind not in OPEN_ENDED_INTENT_KINDS:
        return {}

    # LLM path: requires world contract + LLM
    if llm is not None and isinstance(state.script.get("world"), dict):
        quality = _result_quality(result)
        try:
            raw_patch = _generate_open_ended_patch(llm, action, check, state, quality)
            patch, events = validate_open_ended_patch(raw_patch, state)
        except Exception as exc:
            LOGGER.warning("open-ended content generation failed: %s", exc)
            patch, events = None, None
        if patch is not None or events:
            changes: StateChanges = {}
            if patch is not None:
                changes["runtime_script_patch"] = patch
            if events:
                changes["events"] = [events]
            return changes

    # No-LLM fallback: use script dynamic_entity_templates for discover/create_environment
    if result in {"success", "critical_success"} and intent_kind in NO_LLM_SPAWN_INTENT_KINDS:
        fallback_patch = _no_llm_dynamic_spawn_patch(intent_kind, state)
        if fallback_patch:
            return {"runtime_script_patch": fallback_patch}

    return {}


def _infer_open_ended_intent_kind(action: Action, check: CheckResult) -> str:
    assessment = check.get("assessment", {})
    if isinstance(assessment, dict):
        intent_kind = str(assessment.get("intent_kind") or "").strip()
        if intent_kind in OPEN_ENDED_INTENT_KINDS:
            return intent_kind

    family = str(action.get("intent_family") or action.get("type") or "").strip()
    method = " ".join(
        part for part in (
            str(action.get("raw_input") or "").strip(),
            str(action.get("method_text") or "").strip(),
            str(action.get("method") or "").strip(),
        )
        if part
    )

    if family == "talk" and any(keyword in method for keyword in SOCIAL_HINT_KEYWORDS):
        return "social"
    if family in {"inspect", "wait"} and any(keyword in method for keyword in DISCOVER_HINT_KEYWORDS):
        return "discover"
    if any(keyword in method for keyword in ENVIRONMENT_HINT_KEYWORDS):
        return "create_environment"
    if family == "unknown" and any(keyword in method for keyword in DISCOVER_HINT_KEYWORDS):
        return "discover"
    return ""


def validate_open_ended_patch(
    raw_patch: object,
    state: GameState,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and sanitize an LLM-produced open-ended content patch.

    Returns (patch_dict, events_string). The events_string is extracted from
    the LLM's top-level output and is NOT part of the runtime_script_patch ops.
    """
    world = _world_contract(state)
    try:
        if not isinstance(raw_patch, dict):
            return None, None

        # Extract events early — valid even if ops are empty
        raw_events = raw_patch.get("events")
        events_str = str(raw_events).strip() if isinstance(raw_events, str) and raw_events else None

        # Empty ops is valid when events are present
        ops = raw_patch.get("ops")
        if not isinstance(ops, list) or not ops:
            return None, events_str

        normalized = normalize_runtime_script_patch(raw_patch)  # type: ignore[arg-type]
        allowed_entity_types = set(str(item) for item in world["allowed_entity_types"])
        max_dc = int(world["max_runtime_dc"])
        existing_ids = set(state.script.get("entities", {})) | set(state.entities)
        safe_ops: list[dict[str, Any]] = []

        for op in normalized["ops"]:
            op_name = str(op.get("op") or "")
            if op_name not in OPEN_ENDED_ALLOWED_OPS:
                raise ValueError(f"unsupported open-ended content op: {op_name}")

            if op_name == "add_entity":
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

            elif op_name == "set_flag":
                key = str(op.get("key") or "")
                if not (key.startswith("runtime.") or key.startswith("generated.")):
                    raise ValueError(f"open-ended flag outside runtime/generated namespace: {key}")
                safe_ops.append(deepcopy(op))

        if not safe_ops:
            # Events-only output is valid — return events without patch
            return None, events_str

        patch: dict[str, Any] = {
            "id": str(normalized.get("id") or f"open_ended_{state.turn_id}"),
            "source": OPEN_ENDED_SOURCE,
            "turn_id": state.turn_id,
            "ops": safe_ops,
        }

        return patch, events_str

    except Exception as exc:
        LOGGER.warning("discarding invalid open-ended content patch: %s", exc)
        return None, None


def _result_quality(result: str) -> str:
    """Map d20 result to a semantic quality tier for the LLM prompt."""
    return {
        "critical_success": "excellent",
        "success": "good",
        "fail": "bad",
        "critical_fail": "terrible",
    }.get(result, "unknown")


def _generate_open_ended_patch(
    llm: Any,
    action: Action,
    check: CheckResult,
    state: GameState,
    quality: str,
) -> object:
    """Dispatch to LLM client for open-ended content generation."""
    if hasattr(llm, "generate_content_patch"):
        return llm.generate_content_patch({
            "mode": "open_ended",
            "action": action,
            "check": check,
            "state": state,
            "quality": quality,
        })
    if hasattr(llm, "generate_open_ended_content"):
        return llm.generate_open_ended_content(action, check, state, quality)
    return None


def _no_llm_dynamic_spawn_patch(intent_kind: str, state: GameState) -> dict[str, Any] | None:
    """Build a runtime_script_patch from script-level dynamic_entity_templates.

    When the script has multi-variant templates (e.g. discover, discover_item,
    discover_npc), cycles through all matching entries so each use feels
    different rather than always generating the same entity.
    """
    templates = state.script.get("dynamic_entity_templates", {})
    if templates:
        candidates = sorted(k for k in templates if k == intent_kind or k.startswith(f"{intent_kind}_"))
        if candidates:
            template = templates[candidates[state.turn_id % len(candidates)]]
        else:
            template = FALLBACK_DYNAMIC_SPAWN
    else:
        template = FALLBACK_DYNAMIC_SPAWN

    entity_id = f"dynamic_{intent_kind}_{state.turn_id}"
    entity = deepcopy(template)
    entity.setdefault("name", str(entity_id))
    entity.setdefault("tags", ["dynamic"])
    entity.setdefault("lifecycle", {"category": "persistent"})

    return {
        "id": f"dynamic_spawn_turn_{state.turn_id}",
        "source": OPEN_ENDED_SOURCE,
        "turn_id": state.turn_id,
        "ops": [
            {"op": "add_entity", "id": entity_id, "entity": entity},
        ],
    }
