from __future__ import annotations

from typing import Any


def entity_action_hint(action_type: str, entity_name: str) -> str:
    verb = {
        "attack": "攻击",
        "inspect": "检查",
        "open": "打开",
        "talk": "交谈",
        "take": "拿取",
        "use": "使用道具处理",
        "throw": "投掷道具砸向",
        "interact": "互动",
    }.get(action_type, action_type)
    return f"{verb}{entity_name}"


def scene_action_hint(action_type: str) -> str:
    return {
        "flee": "撤退/拉开距离",
        "wait": "等待/观察局势",
        "move": "移动/靠近目标",
        "unknown": "尝试其他行动",
    }.get(action_type, action_type)


def get_allowed_actions(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata", {})
    if "allowed_actions" in metadata:
        return list(metadata["allowed_actions"])
    return list(metadata.get("actions", {}).keys())
