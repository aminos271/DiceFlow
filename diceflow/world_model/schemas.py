from __future__ import annotations

from typing import Any

# Default world_model config. The time subsystem table is populated here;
# favorability will be added by a later plan.
DEFAULT_WORLD_MODEL: dict[str, Any] = {
    "time": {
        "segments": ["morning", "noon", "evening", "night", "deep_night"],
        "magnitude_table": {"none": 0, "small": 1, "medium": 2, "large": 4},
        "segment_events": {
            "morning": "天色渐明",
            "noon": "日上三竿",
            "evening": "暮色降临",
            "night": "夜幕笼罩",
            "deep_night": "夜深人静",
        },
        "triggers": [
            # More specific (method keyword) triggers first, so e.g. a "wait"
            # whose method says "过夜" jumps overnight instead of +1 segment.
            {"when": {"method_contains": "过夜"}, "advance": {"next_day": True}},
            {"when": {"method_contains": "休息"}, "advance": {"next_day": True}},
            {"when": {"method_contains": "睡"}, "advance": {"next_day": True}},
            {"when": {"action_type": "wait"}, "advance": {"segments": 1}},
            {"when": {"resolution_kind": "transition_attempt"}, "advance": {"segments": 1}},
        ],
    },
}


def get_world_model_config(state: Any) -> dict[str, Any]:
    """Return the world_model config for a GameState.

    Merges DEFAULT_WORLD_MODEL (base) with the script's ``world_model``
    section (override). Returns an empty dict when neither is set.
    """
    script_cfg = state.script.get("world_model", {})
    if not isinstance(script_cfg, dict):
        script_cfg = {}
    return {**DEFAULT_WORLD_MODEL, **script_cfg}


def get_time_config(state: Any) -> dict[str, Any]:
    """Return the time subsystem config, with defaults for missing keys."""
    cfg = get_world_model_config(state).get("time", {})
    if not isinstance(cfg, dict):
        cfg = {}
    defaults = DEFAULT_WORLD_MODEL["time"]
    merged: dict[str, Any] = {}
    for key, default_val in defaults.items():
        merged[key] = cfg[key] if key in cfg else default_val
    return merged
