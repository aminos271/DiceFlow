from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from diceflow.content.worlds.loader import load_world_content, world_exists


EntryType = Literal["world", "location", "character", "event"]
ALL_ENTRY_LISTS = ("world_entries", "location_entries", "character_entries", "event_entries")


@dataclass
class LoreEntry:
    id: str
    type: EntryType
    title: str
    aliases: list[str] = field(default_factory=list)
    summary: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    discovered: bool = False
    source: Literal["script_seed", "manual", "derived"] = "manual"
    linked_entity_id: str | None = None
    linked_turn_ids: list[int] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "aliases": list(self.aliases),
            "summary": self.summary,
            "content": self.content,
            "tags": list(self.tags),
            "pinned": self.pinned,
            "discovered": self.discovered,
            "source": self.source,
            "linked_entity_id": self.linked_entity_id,
            "linked_turn_ids": list(self.linked_turn_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> LoreEntry:
        return LoreEntry(
            id=str(data.get("id", "")),
            type=data.get("type", "world"),
            title=str(data.get("title", "")),
            aliases=[str(a) for a in data.get("aliases", [])],
            summary=str(data.get("summary", "")),
            content=str(data.get("content", "")),
            tags=[str(t) for t in data.get("tags", [])],
            pinned=bool(data.get("pinned", False)),
            discovered=bool(data.get("discovered", False)),
            source=data.get("source", "manual"),
            linked_entity_id=data.get("linked_entity_id"),
            linked_turn_ids=[int(t) for t in data.get("linked_turn_ids", [])],
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


class SessionLore:
    def __init__(self) -> None:
        self.world_entries: list[LoreEntry] = []
        self.location_entries: list[LoreEntry] = []
        self.character_entries: list[LoreEntry] = []
        self.event_entries: list[LoreEntry] = []

    # ── CRUD ───────────────────────────────────────────────────────

    def create_entry(
        self,
        type: EntryType,
        title: str,
        *,
        aliases: list[str] | None = None,
        summary: str = "",
        content: str = "",
        tags: list[str] | None = None,
        pinned: bool = False,
        discovered: bool = False,
        source: Literal["script_seed", "manual", "derived"] = "manual",
        linked_entity_id: str | None = None,
        linked_turn_ids: list[int] | None = None,
    ) -> LoreEntry:
        now = _now_iso()
        entry = LoreEntry(
            id=uuid.uuid4().hex[:12],
            type=type,
            title=title,
            aliases=aliases or [],
            summary=summary,
            content=content,
            tags=tags or [],
            pinned=pinned,
            discovered=discovered,
            source=source,
            linked_entity_id=linked_entity_id,
            linked_turn_ids=linked_turn_ids or [],
            created_at=now,
            updated_at=now,
        )
        self._list_for(entry.type).append(entry)
        return entry

    def get_entry(self, entry_id: str) -> LoreEntry | None:
        for lst in self._all_lists():
            for entry in lst:
                if entry.id == entry_id:
                    return entry
        return None

    def update_entry(self, entry_id: str, **fields: Any) -> LoreEntry | None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return None

        old_type = entry.type
        for key, value in fields.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

        # If type changed, move entry to the correct list
        if "type" in fields and fields["type"] != old_type:
            old_list = self._list_for(old_type)
            if entry in old_list:
                old_list.remove(entry)
            self._list_for(entry.type).append(entry)

        entry.updated_at = _now_iso()
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        for lst in self._all_lists():
            for i, entry in enumerate(lst):
                if entry.id == entry_id:
                    lst.pop(i)
                    return True
        return False

    # ── Query ──────────────────────────────────────────────────────

    def all_entries(self) -> list[LoreEntry]:
        entries: list[LoreEntry] = []
        for lst in self._all_lists():
            entries.extend(lst)
        return entries

    def _all_lists(self) -> tuple[list[LoreEntry], ...]:
        return (self.world_entries, self.location_entries,
                self.character_entries, self.event_entries)

    # ── Script seed ─────────────────────────────────────────────────

    def _is_seeded(self) -> bool:
        return any(
            self.world_entries or self.location_entries
            or self.character_entries or self.event_entries
        )

    def seed_from_script(self, script: dict) -> None:
        """Populate lorebook from script data. Prefers world content
        via world_id, falls back to inline script fields. Idempotent."""
        if self._is_seeded():
            return

        world_id = str(script.get("world_id", ""))
        entities = script.get("entities", {}) if isinstance(script.get("entities"), dict) else {}

        if world_id and world_exists(world_id):
            world_content = load_world_content(world_id)
            if world_content:
                self.seed_from_world_content(world_content, entities)
                return

        # ── Fallback: inline script seed ────────────────────────

        title = str(script.get("title", ""))
        intro = str(script.get("intro", ""))
        scene = script.get("scene", {}) if isinstance(script.get("scene"), dict) else {}
        world_cfg = script.get("world", {}) if isinstance(script.get("world"), dict) else {}

        # ── World entries (background / setting) ────────────────

        # Script overview
        if title or intro:
            self.create_entry(
                type="world",
                title=title or "剧本",
                summary=intro or "",
                content="",
                tags=["script_seed", "world"],
                source="script_seed",
                discovered=True,
            )

        # World background
        premise = str(world_cfg.get("premise", ""))
        tone = str(world_cfg.get("tone", ""))
        if premise or tone:
            parts = []
            if premise:
                parts.append(f"背景: {premise}")
            if tone:
                parts.append(f"氛围: {tone}")
            self.create_entry(
                type="world",
                title="世界背景",
                summary="；".join(parts),
                content="",
                tags=["script_seed", "world", "background"],
                source="script_seed",
            )

        # ── Location entries ────────────────────────────────────

        scene_name = str(scene.get("name", ""))
        scene_desc = str(scene.get("description", ""))
        if scene_name or scene_desc:
            self.create_entry(
                type="location",
                title=scene_name or "初始场景",
                summary=scene_desc,
                content="",
                tags=["script_seed", "location", "scene"],
                source="script_seed",
                discovered=True,
            )

        # ── Character entries ───────────────────────────────────
        for eid, ent in entities.items():
            if not isinstance(ent, dict):
                continue
            etype = str(ent.get("type", ""))
            etags = [str(t) for t in ent.get("tags", [])]
            if etype != "npc" and "npc" not in etags:
                continue
            name = str(ent.get("name", eid))
            personality = ent.get("personality")
            summary_parts = []
            if isinstance(personality, dict):
                traits = personality.get("traits", [])
                manner = personality.get("manner", "")
                motivation = personality.get("motivation", "")
                if traits:
                    summary_parts.append(f"特质: {', '.join(str(t) for t in traits)}")
                if manner:
                    summary_parts.append(f"举止: {manner}")
                if motivation:
                    summary_parts.append(motivation)
            elif isinstance(personality, str):
                summary_parts.append(personality)
            disposition = str(ent.get("disposition", ""))
            if disposition:
                labels = {"hostile": "敌对", "friendly": "友善", "neutral": "中立", "suspicious": "怀疑"}
                summary_parts.append(f"态度: {labels.get(disposition, disposition)}")
            self.create_entry(
                type="character",
                title=name,
                aliases=[str(a) for a in ent.get("aliases", [])],
                summary="；".join(summary_parts) if summary_parts else "",
                content="",
                tags=["script_seed", "character"],
                source="script_seed",
                linked_entity_id=eid,
            )

        # ── Event entries ───────────────────────────────────────
        # No forced seed events in this round.

    def seed_from_world_content(
        self, world_content: dict[str, Any], script_entities: dict[str, Any]
    ) -> None:
        """Seed lorebook from file-based world content."""
        if self._is_seeded():
            return

        default_tags: list[str] = list(world_content.get("meta", {}).get("default_tags", []))

        # ── World entries (background / setting) ────────────────
        for entry_data in world_content.get("world_book", []):
            if not isinstance(entry_data, dict):
                continue
            self.create_entry(
                type="world",
                title=str(entry_data.get("title", entry_data.get("id", ""))),
                aliases=_str_list(entry_data.get("aliases")),
                summary=str(entry_data.get("summary", "")),
                content=str(entry_data.get("content", "")),
                tags=_str_list(entry_data.get("tags")) + default_tags,
                source="script_seed",
                discovered=True,
            )

        # ── Location entries ────────────────────────────────────
        for entry_data in world_content.get("locations", []):
            if not isinstance(entry_data, dict):
                continue
            self.create_entry(
                type="location",
                title=str(entry_data.get("title", entry_data.get("id", ""))),
                aliases=_str_list(entry_data.get("aliases")),
                summary=str(entry_data.get("summary", "")),
                content=str(entry_data.get("content", "")),
                tags=_str_list(entry_data.get("tags")),
                source="script_seed",
                discovered=True,
            )

        # ── Character entries ──────────────────────────────────
        for entry_data in world_content.get("characters", []):
            if not isinstance(entry_data, dict):
                continue
            linked_id = entry_data.get("linked_entity_id")
            if linked_id is not None and str(linked_id) not in script_entities:
                linked_id = None  # Invalidate dangling reference
            self.create_entry(
                type="character",
                title=str(entry_data.get("title", entry_data.get("id", ""))),
                aliases=_str_list(entry_data.get("aliases")),
                summary=str(entry_data.get("summary", "")),
                content=str(entry_data.get("content", "")),
                tags=_str_list(entry_data.get("tags")),
                source="script_seed",
                linked_entity_id=str(linked_id) if linked_id is not None else None,
            )

        # ── Event entries ──────────────────────────────────────
        for entry_data in world_content.get("important_events", []):
            if not isinstance(entry_data, dict):
                continue
            self.create_entry(
                type="event",
                title=str(entry_data.get("title", entry_data.get("id", ""))),
                aliases=_str_list(entry_data.get("aliases")),
                summary=str(entry_data.get("summary", "")),
                content=str(entry_data.get("content", "")),
                tags=_str_list(entry_data.get("tags")),
                source="script_seed",
            )

    def has_script_seed(self) -> bool:
        """True if any entry was sourced from the script seed."""
        all_entries = self.all_entries()
        return any(e.source == "script_seed" for e in all_entries)

    def get_script_seed_entries(self) -> dict[str, list[LoreEntry]]:
        """Return all script_seed entries grouped by type, for Phase 2 consumption."""
        return {
            key: [e for e in lst if e.source == "script_seed"]
            for key, lst in [
                ("world_entries", self.world_entries),
                ("location_entries", self.location_entries),
                ("character_entries", self.character_entries),
                ("event_entries", self.event_entries),
            ]
        }

    def _list_for(self, entry_type: str) -> list[LoreEntry]:
        if entry_type == "location":
            return self.location_entries
        if entry_type == "character":
            return self.character_entries
        if entry_type == "event":
            return self.event_entries
        return self.world_entries

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_entries": [e.to_dict() for e in self.world_entries],
            "location_entries": [e.to_dict() for e in self.location_entries],
            "character_entries": [e.to_dict() for e in self.character_entries],
            "event_entries": [e.to_dict() for e in self.event_entries],
        }

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> SessionLore:
        lore = SessionLore()
        if not isinstance(data, dict):
            return lore
        lore.world_entries = [LoreEntry.from_dict(e) for e in data.get("world_entries", [])]
        lore.location_entries = [LoreEntry.from_dict(e) for e in data.get("location_entries", [])]
        lore.character_entries = [LoreEntry.from_dict(e) for e in data.get("character_entries", [])]
        lore.event_entries = [LoreEntry.from_dict(e) for e in data.get("event_entries", [])]
        return lore


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Phase 2 placeholder ───────────────────────────────────────────

def get_active_lore_entries(lore: SessionLore) -> list[LoreEntry]:
    """Return lore entries that should be active for the current context.

    Phase 2 will filter by discovered status, linked entities, scene, etc.
    For now this is a stub that returns all entries.
    """
    return lore.all_entries()
