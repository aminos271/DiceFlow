from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


EntryType = Literal["world", "character", "event"]


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
    source: Literal["manual", "derived"] = "manual"
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
        source: Literal["manual", "derived"] = "manual",
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
        for lst in (self.world_entries, self.character_entries, self.event_entries):
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
        for lst in (self.world_entries, self.character_entries, self.event_entries):
            for i, entry in enumerate(lst):
                if entry.id == entry_id:
                    lst.pop(i)
                    return True
        return False

    # ── Query ──────────────────────────────────────────────────────

    def all_entries(self) -> list[LoreEntry]:
        entries: list[LoreEntry] = []
        entries.extend(self.world_entries)
        entries.extend(self.character_entries)
        entries.extend(self.event_entries)
        return entries

    def _list_for(self, entry_type: str) -> list[LoreEntry]:
        if entry_type == "character":
            return self.character_entries
        if entry_type == "event":
            return self.event_entries
        return self.world_entries

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "world_entries": [e.to_dict() for e in self.world_entries],
            "character_entries": [e.to_dict() for e in self.character_entries],
            "event_entries": [e.to_dict() for e in self.event_entries],
        }

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> SessionLore:
        lore = SessionLore()
        if not isinstance(data, dict):
            return lore
        lore.world_entries = [LoreEntry.from_dict(e) for e in data.get("world_entries", [])]
        lore.character_entries = [LoreEntry.from_dict(e) for e in data.get("character_entries", [])]
        lore.event_entries = [LoreEntry.from_dict(e) for e in data.get("event_entries", [])]
        return lore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Phase 2 placeholder ───────────────────────────────────────────

def get_active_lore_entries(lore: SessionLore) -> list[LoreEntry]:
    """Return lore entries that should be active for the current context.

    Phase 2 will filter by discovered status, linked entities, scene, etc.
    For now this is a stub that returns all entries.
    """
    return lore.all_entries()
