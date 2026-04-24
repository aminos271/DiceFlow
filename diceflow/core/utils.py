from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base. Both dicts remain unmodified."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def result_label(result: str) -> str:
    return {
        "critical_success": "大成功",
        "success": "成功",
        "fail": "失败",
        "critical_fail": "大失败",
        "impossible": "不可能",
    }.get(result, result)


def traverse_replace(value: Any, leaf_fn: Callable[[Any], Any]) -> Any:
    """Recursively traverse str/list/dict and apply leaf_fn to leaf values.
    leaf_fn is called on every non-container value (not str/list/dict).
    """
    if isinstance(value, str):
        return leaf_fn(value)
    if isinstance(value, list):
        return [traverse_replace(item, leaf_fn) for item in value]
    if isinstance(value, dict):
        return {
            str(traverse_replace(key, leaf_fn)): traverse_replace(item, leaf_fn)
            for key, item in value.items()
        }
    return leaf_fn(value)
