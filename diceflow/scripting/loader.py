from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from diceflow.scripting.archetypes import (
    ENTITY_ARCHETYPES,
    ENTITY_RUNTIME_DEFAULTS,
    materialize_entity,
    materialize_script,
)
from diceflow.scripting.resolver import (
    get_action_spec,
    get_allowed_actions,
    get_entity_action,
    resolve_action_spec,
)
from diceflow.scripting.validation import SCHEMA_VERSION, validate_script


Script = dict[str, Any]
SCRIPT_DIR = Path(__file__).resolve().parent.parent / "content" / "scripts"


def load_script(script_name: str) -> Script:
    script_path = SCRIPT_DIR / f"{script_name}.yaml"
    if not script_path.exists():
        raise FileNotFoundError(f"script not found: {script_name}")

    loaded = yaml.safe_load(script_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"script must be a mapping: {script_name}")

    script = deepcopy(loaded)
    materialize_script(script)
    validate_script(script)
    return script


__all__ = [
    "ENTITY_ARCHETYPES",
    "ENTITY_RUNTIME_DEFAULTS",
    "SCHEMA_VERSION",
    "SCRIPT_DIR",
    "Script",
    "get_action_spec",
    "get_allowed_actions",
    "get_entity_action",
    "load_script",
    "materialize_entity",
    "materialize_script",
    "resolve_action_spec",
    "validate_script",
]
