from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

WORLDS_DIR = Path(__file__).resolve().parent


def world_exists(world_id: str) -> bool:
    return (WORLDS_DIR / world_id).is_dir()


def load_world_meta(world_id: str) -> dict[str, Any] | None:
    world_dir = WORLDS_DIR / world_id
    meta_path = world_dir / "world.json"
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_world_content(world_id: str) -> dict[str, Any] | None:
    world_dir = WORLDS_DIR / world_id
    if not world_dir.is_dir():
        return None

    meta = load_world_meta(world_id)
    if meta is None:
        return None

    return {
        "meta": meta,
        "world_book": _load_yaml_entries(world_dir / "world_book"),
        "locations": _load_yaml_entries(world_dir / "locations"),
        "characters": _load_yaml_entries(world_dir / "characters"),
        "important_events": _load_yaml_entries(world_dir / "important_events"),
    }


def _load_yaml_entries(subdir: Path) -> list[dict[str, Any]]:
    if not subdir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for filepath in sorted(subdir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        if isinstance(raw, dict):
            entries.append(raw)
    return entries
