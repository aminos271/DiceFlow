from __future__ import annotations

from copy import deepcopy
from typing import Any


Script = dict[str, Any]
ENTITY_RUNTIME_DEFAULTS = {
    "visible": True,
    "available": True,
    "destroyed": False,
    "opened": False,
    "looted": False,
}
ENTITY_ARCHETYPES: dict[str, dict[str, Any]] = {
    "container": {
        **ENTITY_RUNTIME_DEFAULTS,
        "contents": [],
        "hooks": {
            "open_critical_success_events": ["你打开了$target_name，里面的东西显露出来。"],
            "open_success_events": ["你打开了$target_name，里面的东西显露出来。"],
            "open_fail_events": ["$target_name卡住了，但你觉得还能再试。"],
            "open_critical_fail_events": ["$target_name突然破裂，碎片划伤了你。"],
            "inspect_success_events": ["你确认$target_name可能藏有物品。"],
        },
        "metadata": {
            "allowed_actions": ["open", "inspect"],
            "actions": {
                "open": {
                    "dc": 10,
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"opened": True}},
                            "reveal_entities": "$contents",
                            "events": "$hook.open_critical_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"opened": True}},
                            "reveal_entities": "$contents",
                            "events": "$hook.open_success_events",
                        },
                        "fail": {
                            "events": "$hook.open_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "events": "$hook.open_critical_fail_events",
                        },
                    },
                },
                "inspect": {
                    "dc": 8,
                    "outcomes": {
                        "success": {
                            "events": "$hook.inspect_success_events",
                        }
                    },
                },
            },
        },
    },
    "door": {
        **ENTITY_RUNTIME_DEFAULTS,
        "locked": True,
        "hooks": {
            "required_tools": [],
            "open_flags": {},
            "use_flags": {},
            "open_critical_success_events": ["$target_name被你顺利打开。"],
            "open_success_events": ["$target_name被打开。"],
            "open_fail_events": ["$target_name卡住了，你需要再试一次。"],
            "open_critical_fail_events": ["你用力过猛，被$target_name反震擦伤。"],
            "use_critical_success_events": ["你用工具顺利打开了$target_name。"],
            "use_success_events": ["工具生效，$target_name被打开。"],
            "use_fail_events": ["工具卡住了，你需要调整角度再试一次。"],
            "use_critical_fail_events": ["你用力过猛，工具滑脱划伤手指。"],
            "inspect_success_events": ["你检查了$target_name。"],
        },
        "metadata": {
            "allowed_actions": ["open", "use", "inspect"],
            "actions": {
                "open": {
                    "dc": 12,
                    "required_tools": "$hook.required_tools",
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.open_flags",
                            "events": "$hook.open_critical_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.open_flags",
                            "events": "$hook.open_success_events",
                        },
                        "fail": {
                            "events": "$hook.open_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "events": "$hook.open_critical_fail_events",
                        },
                    },
                },
                "use": {
                    "dc": 12,
                    "required_tools": "$hook.required_tools",
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.use_flags",
                            "events": "$hook.use_critical_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"opened": True, "locked": False}},
                            "flags": "$hook.use_flags",
                            "events": "$hook.use_success_events",
                        },
                        "fail": {
                            "events": "$hook.use_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "events": "$hook.use_critical_fail_events",
                        },
                    },
                },
                "inspect": {
                    "dc": 8,
                    "outcomes": {
                        "success": {
                            "events": "$hook.inspect_success_events",
                        }
                    },
                },
            },
        },
    },
    "pickup": {
        **ENTITY_RUNTIME_DEFAULTS,
        "hooks": {
            "take_flags": {},
            "take_critical_success_events": ["你立刻捡起$target_name并收好。"],
            "take_success_events": ["你拿起$target_name并收好。"],
            "take_fail_events": ["$target_name暂时卡住了，你需要再试一次。"],
            "inspect_success_events": ["你检查了$target_name。"],
        },
        "metadata": {
            "allowed_actions": ["take", "inspect"],
            "actions": {
                "take": {
                    "dc": 5,
                    "outcomes": {
                        "critical_success": {
                            "move_item_to_inventory": ["$target"],
                            "flags": "$hook.take_flags",
                            "events": "$hook.take_critical_success_events",
                        },
                        "success": {
                            "move_item_to_inventory": ["$target"],
                            "flags": "$hook.take_flags",
                            "events": "$hook.take_success_events",
                        },
                        "fail": {
                            "events": "$hook.take_fail_events",
                        },
                    },
                },
                "inspect": {
                    "dc": 5,
                    "outcomes": {
                        "success": {
                            "events": "$hook.inspect_success_events",
                        }
                    },
                },
            },
        },
    },
}


def materialize_script(script: Script) -> Script:
    script["entities"] = {
        entity_id: materialize_entity(entity, entity_id)
        for entity_id, entity in script.get("entities", {}).items()
    }
    return script


def materialize_entity(entity: dict[str, Any], entity_id: str | None = None) -> dict[str, Any]:
    entity_type = str(entity.get("type") or "")
    base = deepcopy(ENTITY_ARCHETYPES.get(entity_type, ENTITY_RUNTIME_DEFAULTS))
    merged = _deep_merge(base, deepcopy(entity))
    return _render_entity_templates(merged, entity_id)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _render_entity_templates(entity: dict[str, Any], entity_id: str | None) -> dict[str, Any]:
    context = {
        "entity_id": entity_id or "",
        "target_name": str(entity.get("name") or entity_id or "目标"),
        "contents": list(entity.get("contents", [])),
        "hook": entity.get("hooks", {}),
        "item_id": entity.get("item_id") or entity.get("name") or entity_id or "",
    }
    return _render_template_value(entity, context)


def _render_template_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if value == "$contents":
            return list(context["contents"])
        if value == "$item_id":
            return context["item_id"]
        if value.startswith("$hook."):
            return deepcopy(_lookup_path(context["hook"], value.removeprefix("$hook.")))
        return value.replace("$target_name", str(context["target_name"]))
    if isinstance(value, list):
        return [_render_template_value(item, context) for item in value]
    if isinstance(value, dict):
        return {
            str(_render_template_value(key, context)): _render_template_value(item, context)
            for key, item in value.items()
        }
    return value


def _lookup_path(source: Any, path: str) -> Any:
    current = source
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return {}
        current = current[part]
    return current
