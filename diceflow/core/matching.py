from __future__ import annotations

from typing import Any


def matches_value(actual: object, expected: object) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def matches_object(actual: dict[str, object], expected: object) -> bool:
    if not isinstance(expected, dict):
        return False
    for key, expected_value in expected.items():
        if actual.get(str(key)) != expected_value:
            return False
    return True


def matches_all_tags(entity_tags: object, required_tags: object) -> bool:
    tags = entity_tags if isinstance(entity_tags, list) else []
    if isinstance(required_tags, str):
        required_tags = [required_tags]
    elif not isinstance(required_tags, list):
        return False
    return all(tag in tags for tag in required_tags)


def matches_any_tag(entity_tags: object, required_tags: object) -> bool:
    tags = entity_tags if isinstance(entity_tags, list) else []
    if isinstance(required_tags, str):
        required_tags = [required_tags]
    elif not isinstance(required_tags, list):
        return False
    return any(tag in tags for tag in required_tags)
