from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.scripting.archetypes import materialize_entity
from diceflow.scripting.validation import validate_script


Script = dict[str, Any]
RuntimeScriptPatch = dict[str, Any]

SUPPORTED_OPS = {"add_entity", "set_flag"}


def apply_runtime_script_patch(script: Script, patch: RuntimeScriptPatch) -> Script:
    """Return a validated runtime script view with a patch applied."""
    normalized = normalize_runtime_script_patch(patch)
    runtime_script = deepcopy(script)

    for op in normalized["ops"]:
        op_name = op["op"]
        if op_name == "add_entity":
            entity_id = op["id"]
            if entity_id in runtime_script.get("entities", {}):
                raise ValueError(f"runtime script patch cannot overwrite existing entity id: {entity_id}")
            runtime_script.setdefault("entities", {})[entity_id] = materialize_entity(op["entity"], entity_id)
        elif op_name == "set_flag":
            runtime_script.setdefault("flags", {})[op["key"]] = op["value"]
        else:
            raise ValueError(f"unsupported runtime script patch op: {op_name}")

    validate_script(runtime_script)
    return runtime_script


def normalize_runtime_script_patch(patch: RuntimeScriptPatch) -> RuntimeScriptPatch:
    if not isinstance(patch, dict):
        raise ValueError("runtime_script_patch must be a dict")

    patch_id = str(patch.get("id") or "").strip()
    if not patch_id:
        raise ValueError("runtime_script_patch.id is required")

    raw_ops = patch.get("ops")
    if not isinstance(raw_ops, list) or not raw_ops:
        raise ValueError("runtime_script_patch.ops must be a non-empty list")

    ops: list[dict[str, Any]] = []
    seen_entity_ids: set[str] = set()
    for index, raw_op in enumerate(raw_ops):
        if not isinstance(raw_op, dict):
            raise ValueError(f"runtime_script_patch.ops[{index}] must be a dict")
        op_name = str(raw_op.get("op") or "").strip()
        if op_name not in SUPPORTED_OPS:
            raise ValueError(f"unsupported runtime script patch op: {op_name}")

        if op_name == "add_entity":
            entity_id = str(raw_op.get("id") or "").strip()
            if not entity_id:
                raise ValueError(f"runtime_script_patch.ops[{index}].id is required")
            if entity_id in seen_entity_ids:
                raise ValueError(f"runtime script patch has duplicate entity id: {entity_id}")
            entity = raw_op.get("entity")
            if not isinstance(entity, dict):
                raise ValueError(f"runtime_script_patch.ops[{index}].entity must be a dict")
            seen_entity_ids.add(entity_id)
            ops.append({"op": op_name, "id": entity_id, "entity": deepcopy(entity)})
        elif op_name == "set_flag":
            key = str(raw_op.get("key") or "").strip()
            if not key:
                raise ValueError(f"runtime_script_patch.ops[{index}].key is required")
            ops.append({"op": op_name, "key": key, "value": deepcopy(raw_op.get("value"))})

    return {
        "id": patch_id,
        "source": str(patch.get("source") or "runtime"),
        "turn_id": int(patch.get("turn_id") or 0),
        "ops": ops,
    }
