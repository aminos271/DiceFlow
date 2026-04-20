from __future__ import annotations

from typing import Any

from diceflow.models import Action


CANONICAL_INTENT_FAMILIES = {
    "move",
    "inspect",
    "interact",
    "open",
    "use",
    "attack",
    "talk",
    "wait",
    "flee",
    "unknown",
}

LEGACY_TYPE_MAP = {
    "burn": "use",
}

APPROACH_TAG_KEYWORDS = {
    "careful": ["小心", "谨慎", "警惕", "低调", "轻声", "悄悄", "潜行"],
    "forceful": ["用力", "猛", "强行", "撞", "砸"],
    "quick": ["快速", "立刻", "马上", "冲"],
}


def canonical_family(value: str | None) -> str:
    family = str(value or "unknown").strip() or "unknown"
    family = LEGACY_TYPE_MAP.get(family, family)
    if family in CANONICAL_INTENT_FAMILIES:
        return family
    return "unknown"


def action_family(action: Action) -> str:
    return canonical_family(action.get("intent_family") or action.get("type"))


def normalize_action(action: Action, state: Any | None = None) -> Action:
    method_text = str(action.get("method_text") or action.get("method") or "").strip()
    family = canonical_family(action.get("intent_family") or action.get("type"))
    normalized: Action = {
        **action,
        "intent_family": family,
        "type": family,
        "target": str(action.get("target") or "").strip(),
        "tool": str(action.get("tool") or "").strip(),
        "target_id": str(action.get("target_id") or "").strip(),
        "tool_id": str(action.get("tool_id") or "").strip(),
        "approach_tags": list(action.get("approach_tags") or extract_approach_tags(method_text)),
        "method_text": method_text,
    }

    if state:
        if normalized["target"] and not normalized["target_id"]:
            normalized["target_id"] = state.find_entity_id(normalized["target"]) or ""
        if normalized["tool"] and not normalized["tool_id"]:
            normalized["tool_id"] = state.find_inventory_item(normalized["tool"]) or normalized["tool"]

    return normalized


def extract_approach_tags(text: str) -> list[str]:
    tags: list[str] = []
    for tag, keywords in APPROACH_TAG_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)
    return tags
