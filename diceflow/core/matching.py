from __future__ import annotations

from typing import Any


def match_entity_name(name: str, candidates: dict[str, list[str]]) -> str | None:
    """Find the entity_id whose names/aliases uniquely match the given name.

    Candidates format: ``{entity_id: [name, alias1, alias2, ...]}``.

    Two rounds:
    1. Exact: ``normalized == candidate`` → immediate unique match.
       Ambiguous (multiple exact hits) → ``None``.
    2. Constrained substring: checks containment between *normalized* and
       each candidate.  Still returns ``None`` when more than one entity
       matches, avoiding the bare ``str.find`` ambiguity trap (e.g. "门"
       matching both "木门" and "铁门").
    """
    if not name:
        return None

    normalized = name.strip()

    # Round 1 — exact match (name or alias)
    exact_ids: list[str] = []
    for entity_id, names in candidates.items():
        stripped = [n.strip() for n in names]
        if normalized in stripped:
            exact_ids.append(entity_id)

    if len(exact_ids) == 1:
        return exact_ids[0]
    if len(exact_ids) > 1:
        return None  # ambiguous exact match

    # Round 2 — constrained substring (require at least 2 chars)
    if len(normalized) < 2:
        return None

    fuzzy_ids: list[str] = []
    for entity_id, names in candidates.items():
        for n in names:
            if normalized in n or n in normalized:
                fuzzy_ids.append(entity_id)
                break

    if len(fuzzy_ids) == 1:
        return fuzzy_ids[0]
    return None


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
