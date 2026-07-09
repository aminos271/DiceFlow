from __future__ import annotations

from typing import Any

# Default world_model config. Subsystem plans (time, favorability) will
# populate their own default tables here. For now it is an empty skeleton
# so get_world_model_config has a stable base to merge against.
DEFAULT_WORLD_MODEL: dict[str, Any] = {}


def get_world_model_config(state: Any) -> dict[str, Any]:
    """Return the world_model config for a GameState.

    Merges DEFAULT_WORLD_MODEL (base) with the script's ``world_model``
    section (override). Returns an empty dict when neither is set.
    """
    script_cfg = state.script.get("world_model", {})
    if not isinstance(script_cfg, dict):
        script_cfg = {}
    return {**DEFAULT_WORLD_MODEL, **script_cfg}
