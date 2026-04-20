from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from typing import Any


Script = dict[str, Any]


def load_script(script_name: str) -> Script:
    module = import_module(f"diceflow.scripts.{script_name}")
    return deepcopy(module.SCRIPT)


def get_entity_action(script: Script, entity: dict[str, Any], action_type: str) -> dict[str, Any]:
    return entity.get("metadata", {}).get("actions", {}).get(action_type, {})


def get_allowed_actions(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if "allowed_actions" in metadata:
        return list(metadata["allowed_actions"])
    return list(metadata.get("actions", {}).keys())

