from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.utils import deep_merge


Script = dict[str, Any]
ENTITY_RUNTIME_DEFAULTS = {
    "visible": True,
    "available": True,
    "destroyed": False,
    "opened": False,
    "looted": False,
}
ENTITY_ARCHETYPES: dict[str, dict[str, Any]] = {
    "npc": {
        **ENTITY_RUNTIME_DEFAULTS,
        "hp": 6,
        "max_hp": 6,
        "alive": True,
        "hostile": False,
        "faction": "neutral",
        "role": "npc",
        "location": "",
        "favorability": 0,
        "disposition": "neutral",
        "personality": {
            "traits": [],
            "manner": "",
            "motivation": "",
        },
        "inventory": [],
        "equipped": {},
        "attributes": {
            "strength": 10,
            "agility": 10,
            "endurance": 10,
            "intellect": 10,
            "will": 10,
            "charm": 10,
        },
        "goals": [],
        "memory": [],
        "tags": ["npc"],
        "hooks": {
            "attack_success_events": ["你击中了$target_name。"],
            "attack_fail_events": ["$target_name避开了攻击。"],
            "talk_success_events": ["$target_name愿意继续听你说。"],
            "talk_fail_events": ["$target_name对你的态度没有改善。"],
            "inspect_success_events": ["你观察了$target_name，判断出对方的态度和状态。"],
        },
        "metadata": {
            "allowed_actions": ["talk", "inspect", "attack"],
            "actions": {
                "talk": {
                    "dc": 10,
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"favorability_delta": 2, "hostile": False}},
                            "events": "$hook.talk_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"favorability_delta": 1}},
                            "events": "$hook.talk_success_events",
                        },
                        "fail": {
                            "events": "$hook.talk_fail_events",
                        },
                        "critical_fail": {
                            "entities": {"$target": {"favorability_delta": -2, "hostile": True}},
                            "events": "$hook.talk_fail_events",
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
                "attack": {
                    "dc": 12,
                    "outcomes": {
                        "critical_success": {
                            "entities": {"$target": {"hp_delta": -5, "hostile": True}},
                            "events": "$hook.attack_success_events",
                        },
                        "success": {
                            "entities": {"$target": {"hp_delta": -3, "hostile": True}},
                            "events": "$hook.attack_success_events",
                        },
                        "fail": {
                            "events": "$hook.attack_fail_events",
                        },
                        "critical_fail": {
                            "player": {"hp_delta": -1},
                            "entities": {"$target": {"hostile": True}},
                            "events": "$hook.attack_fail_events",
                        },
                    },
                },
            },
        },
    },
    "item": {
        **ENTITY_RUNTIME_DEFAULTS,
        "item_id": "$item_id",
        "source": "",
        "holder_id": "",
        "quantity": 1,
        "stackable": False,
        "weight": 1,
        "value": 0,
        "rarity": "common",
        "durability": None,
        "properties": {},
        "effects": [],
        "tags": ["item"],
        "hooks": {
            "take_flags": {},
            "take_critical_success_events": ["你立刻拿起$target_name并收好。"],
            "take_success_events": ["你拿起$target_name并收好。"],
            "take_fail_events": ["$target_name暂时卡住了，你需要再试一次。"],
            "inspect_success_events": ["你检查了$target_name。"],
        },
        "metadata": {
            "allowed_actions": ["take", "inspect", "use"],
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
                "use": {
                    "dc": 10,
                    "outcomes": {
                        "success": {
                            "events": ["你使用了$target_name。"],
                        },
                        "fail": {
                            "events": ["$target_name没有产生明确效果。"],
                        },
                    },
                },
            },
        },
    },
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
    merged = deep_merge(base, deepcopy(entity))
    return _render_entity_templates(merged, entity_id)




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
