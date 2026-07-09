from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import yaml

from diceflow.app.game import META_HELP, META_HINT, META_INV, META_LOOK, META_STATUS
from diceflow.content.worlds.loader import WORLDS_DIR, load_world_meta, world_exists
from diceflow.web import SessionStore

app = FastAPI(title="DiceFlow API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = SessionStore()


# ── Request/Response models ───────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    script_id: str | None = None
    world_id: str | None = None
    use_llm: bool = True


class TurnRequest(BaseModel):
    input: str
    force_critical: bool = False
    forced_roll: int | None = None


class MetaRequest(BaseModel):
    command: str


class WorldInfo(BaseModel):
    id: str
    title: str
    description: str


class WorldCreateRequest(BaseModel):
    id: str | None = None
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    intro: str = ""
    scene_name: str = Field(default="起点", max_length=80)
    scene_description: str = ""
    premise: str = ""
    tone: str = ""
    player_inventory: list[str] = Field(default_factory=list)
    initial_npc_name: str | None = Field(default=None, max_length=80)
    initial_npc_summary: str = ""
    bootstrap_yaml: str = ""


class ScriptInfo(BaseModel):
    id: str
    title: str
    intro: str


class SessionSummary(BaseModel):
    session_id: str
    script_id: str | None = None
    world_id: str | None = None
    display_name: str = ""
    created_at: str
    updated_at: str
    turn_count: int
    ending: str | None = None


class UpdateSessionRequest(BaseModel):
    display_name: str | None = None


class UpdateEntityRequest(BaseModel):
    patch: dict[str, Any]


class LoreEntryCreate(BaseModel):
    type: Literal["world", "location", "character", "event"]
    title: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    pinned: bool = False
    discovered: bool = False
    source: Literal["script_seed", "manual", "derived"] = "manual"
    linked_entity_id: str | None = None
    linked_turn_ids: list[int] = Field(default_factory=list)


class LoreEntryUpdate(BaseModel):
    type: Literal["world", "location", "character", "event"] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=80)
    aliases: list[str] | None = None
    summary: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    discovered: bool | None = None
    source: Literal["script_seed", "manual", "derived"] | None = None
    linked_entity_id: str | None = None
    linked_turn_ids: list[int] | None = None


class StatusData(BaseModel):
    turn_id: int
    hp: int
    max_hp: int
    inventory: list[str]
    scene_name: str
    scene_description: str
    visible_entities: list[dict[str, Any]]
    known_entities: list[dict[str, Any]]
    hostile_count: int
    hints: list[str]
    hint_groups: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    threads: list[dict[str, Any]] = Field(default_factory=list)
    exits: list[dict[str, str]] = Field(default_factory=list)
    is_game_over: bool = False
    ending: str | None = None
    world_clock: dict[str, Any] = Field(default_factory=dict)


# ── API Endpoints ─────────────────────────────────────────────────────

@app.get("/api/scripts")
def list_scripts() -> list[ScriptInfo]:
    return []


@app.get("/api/worlds")
def list_worlds() -> list[WorldInfo]:
    worlds: list[WorldInfo] = []
    if not WORLDS_DIR.is_dir():
        return worlds
    # Always include default bootstrap
    worlds.append(WorldInfo(
        id="_default",
        title="边境旅店",
        description="温暖的炉火、吧台后的旅店老板、各路冒险者的故事——从这里开始你的旅程。",
    ))
    for world_dir in sorted(WORLDS_DIR.iterdir()):
        if not world_dir.is_dir() or world_dir.name.startswith("_"):
            continue
        world_id = world_dir.name
        if not world_exists(world_id):
            continue
        meta = load_world_meta(world_id)
        if meta:
            worlds.append(WorldInfo(
                id=str(meta.get("id") or world_id),
                title=str(meta.get("title") or world_id),
                description=str(meta.get("description") or ""),
            ))
    return worlds


@app.post("/api/worlds")
def create_world(body: WorldCreateRequest) -> dict[str, Any]:
    world_id = _normalize_world_id(body.id, body.title)
    world_dir = WORLDS_DIR / world_id
    if world_dir.exists():
        raise HTTPException(status_code=409, detail=f"world already exists: {world_id}")

    bootstrap = _build_world_bootstrap(body, world_id)
    meta = {
        "id": world_id,
        "title": body.title.strip(),
        "description": body.description.strip(),
        "script_ids": [],
        "default_tags": _default_tags_for_world(body),
    }

    try:
        world_dir.mkdir(parents=True, exist_ok=False)
        (world_dir / "world_book").mkdir(exist_ok=True)
        (world_dir / "locations").mkdir(exist_ok=True)
        (world_dir / "characters").mkdir(exist_ok=True)
        (world_dir / "important_events").mkdir(exist_ok=True)

        (world_dir / "world.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (world_dir / "bootstrap.yaml").write_text(
            yaml.safe_dump(bootstrap, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        _write_seed_files(world_dir, body, bootstrap)
    except Exception:
        _remove_world_dir(world_dir)
        raise

    return {
        "world": {
            "id": world_id,
            "title": meta["title"],
            "description": meta["description"],
        }
    }


@app.post("/api/sessions")
def create_session(body: CreateSessionRequest) -> dict[str, Any]:
    if body.script_id:
        raise HTTPException(status_code=422, detail="script-driven sessions have been removed; use world_id")
    try:
        session = store.create(script_id=None, world_id=body.world_id, use_llm=body.use_llm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "session_id": session.session_id,
        "script_id": session.script_id,
        "world_id": session.world_id,
        "display_name": session.display_name,
        "created_at": session.created_at,
    }


@app.get("/api/sessions")
def list_sessions() -> list[SessionSummary]:
    return [SessionSummary(**s) for s in store.list_sessions()]


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    d = session.to_dict()
    d["status"] = _build_status(session)
    return d


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: str, body: UpdateSessionRequest) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="display_name must not be empty")
        if len(name) > 40:
            raise HTTPException(status_code=422, detail="display_name must be at most 40 characters")
        session.display_name = name
        store.save_to_disk(session)
    return {"session_id": session.session_id, "display_name": session.display_name}


@app.patch("/api/sessions/{session_id}/entities/{entity_id}")
def update_entity(session_id: str, entity_id: str, body: UpdateEntityRequest) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    entity = session.game.state.entities.get(entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"entity not found: {entity_id}")
    editable_reason = _editable_entity_error(session, entity_id, entity)
    if editable_reason:
        raise HTTPException(status_code=409, detail=editable_reason)
    try:
        session.game.state.update_entity(entity_id, body.patch)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"entity not found: {entity_id}") from None
    store.save_to_disk(session)
    return {"entity": _entity_record(session, entity_id, session.game.state.entities[entity_id])}


# ── Lorebook endpoints ─────────────────────────────────────────────


@app.get("/api/sessions/{session_id}/lorebook")
def get_lorebook(session_id: str) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return {"entries": session.lorebook.to_dict()}


@app.post("/api/sessions/{session_id}/lorebook")
def create_lore_entry(session_id: str, body: LoreEntryCreate) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    # Validate linked_entity_id references a real entity if set
    _validate_linked_entity(session, body.linked_entity_id)
    entry = session.lorebook.create_entry(
        type=body.type,
        title=body.title,
        aliases=body.aliases,
        summary=body.summary,
        content=body.content,
        tags=body.tags,
        pinned=body.pinned,
        discovered=body.discovered,
        source=body.source,
        linked_entity_id=body.linked_entity_id,
        linked_turn_ids=body.linked_turn_ids,
    )
    store.save_to_disk(session)
    return {"entry": entry.to_dict()}


@app.patch("/api/sessions/{session_id}/lorebook/{entry_id}")
def update_lore_entry(session_id: str, entry_id: str, body: LoreEntryUpdate) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    # Use exclude_unset so that explicit null values (e.g. linked_entity_id=null)
    # are passed through instead of being dropped by exclude_none.
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    if "linked_entity_id" in fields:
        _validate_linked_entity(session, fields.get("linked_entity_id"))
    entry = session.lorebook.update_entry(entry_id, **fields)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"lore entry not found: {entry_id}")
    store.save_to_disk(session)
    return {"entry": entry.to_dict()}


@app.delete("/api/sessions/{session_id}/lorebook/{entry_id}")
def delete_lore_entry(session_id: str, entry_id: str) -> dict[str, str]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    if not session.lorebook.delete_entry(entry_id):
        raise HTTPException(status_code=404, detail=f"lore entry not found: {entry_id}")
    store.save_to_disk(session)
    return {"status": "deleted", "entry_id": entry_id}


# ── Session lifecycle ──────────────────────────────────────────────


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, str]:
    if not store.delete(session_id):
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return {"status": "deleted", "session_id": session_id}


@app.post("/api/sessions/{session_id}/delete")
def delete_session_via_post(session_id: str) -> dict[str, str]:
    return delete_session(session_id)


@app.post("/api/sessions/{session_id}/turns")
def run_turn(session_id: str, body: TurnRequest) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    state = session.game.state
    if state.flags.get("game_over"):
        raise HTTPException(status_code=400, detail="game is already over")

    if body.forced_roll is not None:
        forced_roll = body.forced_roll
    elif body.force_critical:
        forced_roll = 20
    else:
        forced_roll = None
    record = session.game.run_turn(body.input, forced_roll=forced_roll)
    session.turn_history.append(record.to_dict())
    store.save_to_disk(session)

    return {
        "turn": record.to_dict(),
        "status": _build_status(session),
        "is_game_over": bool(state.flags.get("game_over")),
        "ending": state.flags.get("ending"),
    }


@app.post("/api/sessions/{session_id}/meta")
def run_meta(session_id: str, body: MetaRequest) -> dict[str, Any]:
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    state = session.game.state
    cmd = body.command.strip().lower()

    if cmd in META_HELP:
        return {"result": _help_text()}
    if cmd in META_LOOK:
        return {"result": "你环顾四周。", "status": _build_status(session)}
    if cmd in META_INV:
        items = state.get_inventory_items()
        return {"result": "、".join(items) if items else "背包空空如也。", "status": _build_status(session)}
    if cmd in META_STATUS:
        return {"result": "", "status": _build_status(session)}
    if cmd in META_HINT:
        hints = state.get_available_action_hints()
        return {"result": "；".join(hints) if hints else "检查周围；等待/观察局势", "status": _build_status(session)}
    raise HTTPException(status_code=400, detail=f"unknown meta command: {body.command}")


# ── Health check ──────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ── Helpers ───────────────────────────────────────────────────────────

def _build_known_entities(session) -> list[dict[str, Any]]:
    """Build a record of entities the player knows about.

    "Known" means the player has seen, picked up, or otherwise interacted
    with the entity.  Hidden entities that have never been revealed are
    intentionally excluded to avoid leaking script secrets.

    Sources (in priority order):
      1. Currently visible entities (get_visible_entities)
      2. Items in player inventory
      3. Entities recorded in entity_journal (removed / expired)
      4. Non-visible entities whose lifecycle shows evidence of prior
         interaction (updated_turn_id, looted, destroyed, phase changes)
    """
    state = session.game.state
    inventory_names = set(state.get_inventory_items())
    visible = state.get_visible_entities()

    # ── Determine which entity IDs are known ──────────────────────
    known_ids: set[str] = set()

    # 1. Currently visible entities are always known
    known_ids.update(visible.keys())

    # 2. Entities referenced in entity_journal (removed / TTL-expired)
    journal_by_entity: dict[str, dict[str, Any]] = {}
    for je in state.entity_journal:
        eid = je.get("entity_id")
        if eid:
            journal_by_entity[eid] = je
            known_ids.add(eid)

    # 3. Non-visible entities with evidence of prior interaction
    for eid, ent in state.entities.items():
        if eid in known_ids:
            continue
        name = str(ent.get("name", eid))
        # In player inventory
        if name in inventory_names:
            known_ids.add(eid)
            continue
        # Looted / moved to inventory phase
        if ent.get("looted") or ent.get("lifecycle", {}).get("phase") == "inventory":
            known_ids.add(eid)
            continue
        # Destroyed — the player must have interacted with it
        if ent.get("destroyed"):
            known_ids.add(eid)
            continue
        # Lifecycle updated_turn_id indicates the entity's state was
        # touched by a game action (reveal, hide, damage, etc.)
        updated_turn = ent.get("lifecycle", {}).get("updated_turn_id")
        if updated_turn is not None and updated_turn > 0:
            known_ids.add(eid)
            continue

    # ── Build records ─────────────────────────────────────────────
    records: list[dict[str, Any]] = []
    recorded_names: set[str] = set()

    for eid in known_ids:
        ent = state.entities.get(eid)
        if ent is None:
            # Entity was removed — rebuild minimal record from journal
            je = journal_by_entity.get(eid)
            if not je:
                continue
            lifecycle = je.get("lifecycle", {}) if isinstance(je.get("lifecycle"), dict) else {}
            name = str(je.get("name", eid))
            in_inv = lifecycle.get("phase") == "inventory" or name in inventory_names
            records.append({
                "id": eid,
                "name": name,
                "type": "",
                "tags": [],
                "is_visible": False,
                "is_in_inventory": in_inv,
                "hostile": False,
                "locked": False,
                "opened": False,
                "destroyed": lifecycle.get("phase") == "destroyed",
                "looted": lifecycle.get("phase") == "inventory",
                "alive": lifecycle.get("phase") not in ("destroyed", "removed"),
                "available": False,
                "last_seen_turn_id": je.get("turn_id"),
                "last_interaction_turn_id": lifecycle.get("last_player_interaction_turn_id"),
                "turns_since_interaction": _turns_since_interaction(state, lifecycle),
                "can_edit": False,
            })
            recorded_names.add(name)
            continue

        # Active entity in state.entities
        name = str(ent.get("name", eid))
        records.append(_entity_record(session, eid, ent, journal_entry=journal_by_entity.get(eid)))
        recorded_names.add(name)

    # Add inventory-only items that have no corresponding entity
    for item_name in inventory_names:
        if item_name not in recorded_names:
            records.append({
                "id": item_name,
                "name": item_name,
                "type": "item",
                "tags": [],
                "is_visible": False,
                "is_in_inventory": True,
                "hostile": False,
                "locked": False,
                "opened": False,
                "destroyed": False,
                "looted": True,
                "alive": True,
                "available": False,
                "last_seen_turn_id": state.turn_id,
                "last_interaction_turn_id": None,
                "turns_since_interaction": None,
                "can_edit": False,
            })

    return records


def _build_status(session) -> StatusData:
    state = session.game.state
    scene = state.get_current_scene()
    visible = state.get_visible_entities()
    hostile_count = len(state.get_hostile_entities())

    entity_list: list[dict[str, Any]] = []
    for eid, ent in visible.items():
        info: dict[str, Any] = {
            "id": eid,
            "name": ent.get("name", eid),
            "type": ent.get("type", ""),
            "tags": ent.get("tags", []),
        }
        if "hp" in ent:
            info["hp"] = ent["hp"]
            info["max_hp"] = ent.get("max_hp", ent["hp"])
        if ent.get("hostile") or "hostile" in ent.get("tags", []):
            info["hostile"] = True
        if ent.get("locked"):
            info["locked"] = True
        if ent.get("opened"):
            info["opened"] = True
        if ent.get("destroyed"):
            info["destroyed"] = True
        if ent.get("type") == "npc" or "npc" in ent.get("tags", []):
            info["disposition"] = ent.get("disposition", "neutral")
            info["favorability"] = ent.get("favorability", 0)
            personality = ent.get("personality")
            if isinstance(personality, dict):
                info["personality"] = {
                    "traits": personality.get("traits", []),
                    "manner": personality.get("manner", ""),
                    "motivation": personality.get("motivation", ""),
                }
            elif isinstance(personality, str):
                info["personality"] = {"traits": [], "manner": personality, "motivation": ""}
        entity_list.append(info)

    exit_hints = _exit_movement_hints(state)
    all_hints = exit_hints + (state.get_available_action_hints() or ["检查周围", "等待/观察局势"])

    return StatusData(
        turn_id=state.turn_id,
        hp=state.player.get("hp", 0),
        max_hp=state.player.get("max_hp", 1),
        inventory=state.get_inventory_items(),
        scene_name=str(scene.get("name", state.get_current_scene_id())),
        scene_description=str(scene.get("description", "")),
        visible_entities=entity_list,
        known_entities=_build_known_entities(session),
        hostile_count=hostile_count,
        hints=all_hints,
        hint_groups=_build_hint_groups(state, exit_hints),
        threads=_build_thread_list(state),
        exits=_build_exit_list(state),
        is_game_over=bool(state.flags.get("game_over")),
        ending=state.flags.get("ending"),
        world_clock=dict(state.world_clock),
    )


def _build_hint_groups(state, exit_hints: list[str] | None = None) -> dict[str, list[dict[str, str]]]:
    hints = state.get_available_action_hints() or ["检查周围", "等待/观察局势"]
    groups: dict[str, list[dict[str, str]]] = {"recommended": [], "explore": [], "risky": []}
    for hint in exit_hints or []:
        groups["explore"].append({
            "label": hint,
            "detail": "前往已知地点，不需要重新生成场景",
            "command": hint,
        })
    for hint in hints:
        text = str(hint)
        detail = _hint_detail(text, state)
        item = {"label": text, "detail": detail, "command": _hint_command(text, detail)}
        if _is_risky_hint(text):
            groups["risky"].append(item)
        elif _is_explore_hint(text):
            groups["explore"].append(item)
        else:
            groups["recommended"].append(item)
    return {key: value for key, value in groups.items() if value}


def _build_thread_list(state) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for thread in state.threads.values():
        if not thread.discovered:
            continue
        if thread.status == "active":
            result.append(thread.to_dict())
        elif thread.status in ("completed", "failed"):
            if state.turn_id - thread.last_updated_turn_id <= 3:
                result.append(thread.to_dict())
    result.sort(key=lambda t: (0 if t["status"] == "active" else 1, -t["last_updated_turn_id"]))
    return result


def _hint_detail(hint: str, state) -> str:
    if "尸体" in hint or "搜索" in hint or "搜刮" in hint:
        return "可能找到钥匙、线索或可用装备"
    if "盾牌" in hint:
        return "获得防御能力，解锁格挡动作"
    if "左门" in hint or "门" in hint:
        if "打开" in hint or "撬" in hint or "撞" in hint or "强行" in hint:
            return "速度快，但可能触发陷阱或惊动敌人"
        return "判断门后风险，确认锁和冷光来源"
    if "火把" in hint:
        return "照亮黑暗区域，也可检查暗处或威吓"
    if "攻击" in hint:
        return "普通伤害，直接削弱敌人"
    if "交谈" in hint:
        return "可能降低敌意，避免继续战斗"
    if "检查" in hint or "观察" in hint:
        return "获取弱点、线索或环境信息"
    if "撤退" in hint or "拉开" in hint:
        return "脱离压迫，但可能被追击"
    if state.get_hostile_entities():
        return "推进当前局势，同时承担战斗风险"
    return "推进探索并发现新的可互动入口"


def _hint_command(hint: str, detail: str) -> str:
    clean = hint.replace("/", "或")
    if detail:
        return f"我想{clean}，{detail}。"
    return f"我想{clean}。"


def _is_risky_hint(hint: str) -> bool:
    return any(word in hint for word in ("强行", "撞", "撬", "撤退", "逃", "攻击"))


def _is_explore_hint(hint: str) -> bool:
    return any(word in hint for word in ("检查", "观察", "等待", "倾听", "搜索", "搜刮"))


def _entity_record(session, entity_id: str, ent: dict[str, Any], journal_entry: dict[str, Any] | None = None) -> dict[str, Any]:
    state = session.game.state
    inventory_names = set(state.get_inventory_items())
    visible = state.get_visible_entities()
    name = str(ent.get("name", entity_id))
    is_vis = entity_id in visible
    in_inv = name in inventory_names or ent.get("lifecycle", {}).get("phase") == "inventory"

    if is_vis:
        last_seen = state.turn_id
    elif journal_entry:
        last_seen = journal_entry.get("turn_id")
    else:
        last_seen = ent.get("lifecycle", {}).get("updated_turn_id")

    lifecycle = ent.get("lifecycle", {}) if isinstance(ent.get("lifecycle"), dict) else {}
    turns_since = _turns_since_interaction(state, lifecycle)
    record: dict[str, Any] = {
        "id": entity_id,
        "name": name,
        "type": ent.get("type", ""),
        "tags": ent.get("tags", []),
        "is_visible": is_vis,
        "is_in_inventory": in_inv,
        "hostile": bool(ent.get("hostile") or "hostile" in ent.get("tags", [])),
        "locked": bool(ent.get("locked")),
        "opened": bool(ent.get("opened")),
        "destroyed": bool(ent.get("destroyed")),
        "looted": bool(ent.get("looted")),
        "alive": bool(ent.get("alive", True)),
        "available": bool(ent.get("available", True)),
        "last_seen_turn_id": last_seen,
        "last_interaction_turn_id": lifecycle.get("last_player_interaction_turn_id"),
        "turns_since_interaction": turns_since,
        "can_edit": _editable_entity_error(session, entity_id, ent) is None,
        "relationship_history_count": len(
            (ent.get("relationship") or {}).get("history", [])
        ) if isinstance(ent.get("relationship"), dict) else 0,
    }
    if "hp" in ent:
        record["hp"] = ent["hp"]
        record["max_hp"] = ent.get("max_hp", ent["hp"])
    if ent.get("type") == "npc" or "npc" in ent.get("tags", []):
        record["disposition"] = ent.get("disposition", "neutral")
        record["favorability"] = ent.get("favorability", 0)
        personality = ent.get("personality")
        if isinstance(personality, dict):
            record["personality"] = {
                "traits": personality.get("traits", []),
                "manner": personality.get("manner", ""),
                "motivation": personality.get("motivation", ""),
            }
        elif isinstance(personality, str):
            record["personality"] = {"traits": [], "manner": personality, "motivation": ""}
        memories = state.get_memories_for_npc(entity_id)
        if memories:
            record["recent_memories"] = memories[:5]
    return record


def _turns_since_interaction(state, lifecycle: dict[str, Any]) -> int | None:
    last_turn = lifecycle.get("last_player_interaction_turn_id")
    if last_turn is None:
        return None
    return max(0, state.turn_id - int(last_turn))


def _editable_entity_error(session, entity_id: str, ent: dict[str, Any]) -> str | None:
    del entity_id
    tags = {str(tag) for tag in ent.get("tags", [])}
    entity_type = str(ent.get("type") or "")
    if entity_type not in {"npc", "item", "pickup", "container", "obstacle"} and "npc" not in tags:
        return "只有 NPC 或物品类实体支持手动编辑"
    lifecycle = ent.get("lifecycle", {}) if isinstance(ent.get("lifecycle"), dict) else {}
    turns_since = _turns_since_interaction(session.game.state, lifecycle)
    if turns_since is None or turns_since < 3:
        return "该实体距离上次互动不足 3 回合，暂不可编辑"
    return None


def _validate_linked_entity(session, linked_entity_id: str | None) -> None:
    """Raise 422 if linked_entity_id is non-null and not a known entity."""
    if linked_entity_id is None:
        return
    if linked_entity_id not in session.game.state.entities:
        raise HTTPException(
            status_code=422,
            detail=f"linked_entity_id references unknown entity: {linked_entity_id}",
        )


def _normalize_world_id(raw_id: str | None, title: str) -> str:
    text = (raw_id or "").strip().lower()
    if not text:
        ascii_slug = re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")
        text = ascii_slug or f"world_{uuid.uuid4().hex[:8]}"
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    if not text:
        text = f"world_{uuid.uuid4().hex[:8]}"
    if text.startswith("_") and text != "_default":
        text = text.lstrip("_") or f"world_{uuid.uuid4().hex[:8]}"
    return text


def _build_world_bootstrap(body: WorldCreateRequest, world_id: str) -> dict[str, Any]:
    if body.bootstrap_yaml.strip():
        try:
            parsed = yaml.safe_load(body.bootstrap_yaml)
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=422, detail=f"bootstrap_yaml 解析失败: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=422, detail="bootstrap_yaml 必须是 YAML 对象")
        parsed.setdefault("player", {"hp": 10, "max_hp": 10, "inventory": [], "location": body.scene_name})
        parsed.setdefault("scene", {"name": body.scene_name, "description": body.scene_description})
        parsed.setdefault("flags", {"game_over": False, "ending": ""})
        parsed.setdefault("world", {})
        parsed.setdefault("entities", {})
        parsed.setdefault("scene_actions", {})
        parsed.setdefault("ending_conditions", [
            {"when": {"turn_id_gte": 20}, "ending": "timeout"},
            {"when": {"player_hp_lte": 0}, "ending": "death"},
        ])
        return parsed

    npc_entities: dict[str, Any] = {}
    if body.initial_npc_name and body.initial_npc_name.strip():
        npc_entities["npc_1"] = {
            "name": body.initial_npc_name.strip(),
            "type": "npc",
            "hp": 5,
            "max_hp": 5,
            "alive": True,
            "favorability": 0,
            "disposition": "neutral",
            "personality": {
                "traits": ["谨慎"],
                "manner": "先观察再回应",
                "motivation": body.initial_npc_summary.strip() or "想先判断你是否可信。",
            },
            "tags": ["npc"],
            "metadata": {
                "allowed_actions": ["talk", "inspect"],
                "actions": {
                    "talk": {
                        "dc": 8,
                        "outcomes": {
                            "success": {"events": [f"{body.initial_npc_name.strip()}愿意继续和你交谈。"]},
                            "fail": {"events": [f"{body.initial_npc_name.strip()}只是敷衍地点了点头。"]},
                        },
                    },
                    "inspect": {
                        "dc": 6,
                        "outcomes": {
                            "success": {"events": [f"你注意到{body.initial_npc_name.strip()}似乎在有意隐藏情绪。"]},
                        },
                    },
                },
            },
        }

    return {
        "title": body.title.strip(),
        "intro": body.intro.strip() or body.description.strip() or f"你来到{body.title.strip()}。",
        "player": {
            "hp": 10,
            "max_hp": 10,
            "inventory": list(body.player_inventory),
            "location": body.scene_name.strip() or "起点",
        },
        "scene": {
            "name": body.scene_name.strip() or "起点",
            "description": body.scene_description.strip() or body.description.strip(),
        },
        "flags": {"game_over": False, "ending": ""},
        "world": {
            "premise": body.premise.strip() or body.description.strip(),
            "tone": body.tone.strip(),
            "allowed_scene_types": ["tavern", "street", "corridor", "chamber", "wilderness"],
            "allowed_entity_types": ["npc", "pickup", "container", "door", "obstacle", "clue", "item"],
            "forbidden": [],
            "max_runtime_dc": 14,
            "max_new_entities_per_transition": 3,
        },
        "entities": npc_entities,
        "scene_actions": {
            "wait": {
                "dc": 6,
                "outcomes": {
                    "success": {"events": ["你暂时按兵不动，观察局势的变化。"]},
                    "fail": {"events": ["你等了一会，但暂时没有新的变化。"]},
                },
            },
            "inspect": {
                "dc": 8,
                "outcomes": {
                    "success": {"events": ["你耐心地观察周围，找到了一些可继续追查的细节。"]},
                    "fail": {"events": ["你四下查看，但一时没有发现新的收获。"]},
                },
            },
        },
        "dynamic_entity_templates": {
            "discover_clue": {
                "type": "clue",
                "name": "新发现的线索",
                "aliases": ["线索", "痕迹"],
                "tags": ["clue", "dynamic"],
                "metadata": {
                    "allowed_actions": ["inspect"],
                    "actions": {
                        "inspect": {
                            "dc": 8,
                            "outcomes": {
                                "success": {"events": ["这条线索让你对当前世界有了更明确的判断。"]},
                            },
                        }
                    },
                },
            },
            "social": {
                "type": "npc",
                "name": "路过的旅人",
                "tags": ["npc", "dynamic"],
            },
        },
        "ending_conditions": [
            {"when": {"turn_id_gte": 20}, "ending": "timeout"},
            {"when": {"player_hp_lte": 0}, "ending": "death"},
        ],
        "default_no_outcome_event": "局势发生了变化，你必须立刻决定下一步。",
        "invalid_action_event": "行动没有成立，但世界并不会因此停下。",
        "ending_texts": {
            "timeout": "你拖得太久，机会从指缝间溜走了。",
            "death": "你的冒险到此为止。",
        },
    }


def _default_tags_for_world(body: WorldCreateRequest) -> list[str]:
    tags = []
    if body.tone.strip():
        tags.append(body.tone.strip())
    if body.scene_name.strip():
        tags.append(body.scene_name.strip())
    tags.append("自定义")
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag and tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _write_seed_files(world_dir: Path, body: WorldCreateRequest, bootstrap: dict[str, Any]) -> None:
    overview = {
        "id": "overview",
        "title": f"{body.title.strip()}概览",
        "summary": body.description.strip(),
        "content": body.premise.strip() or body.description.strip(),
        "tags": ["自定义", "概览"],
    }
    (world_dir / "world_book" / "overview.yaml").write_text(
        yaml.safe_dump(overview, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    location = {
        "id": "start",
        "title": body.scene_name.strip() or "起点",
        "aliases": [body.scene_name.strip() or "起点"],
        "summary": body.scene_description.strip(),
        "content": body.scene_description.strip(),
        "tags": ["起点", "自定义"],
    }
    (world_dir / "locations" / "start.yaml").write_text(
        yaml.safe_dump(location, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    entities = bootstrap.get("entities", {})
    if isinstance(entities, dict):
        for entity_id, entity in entities.items():
            if not isinstance(entity, dict):
                continue
            entity_tags = [str(tag) for tag in entity.get("tags", [])]
            if str(entity.get("type") or "") != "npc" and "npc" not in entity_tags:
                continue
            personality = entity.get("personality", {}) if isinstance(entity.get("personality"), dict) else {}
            summary_parts = []
            traits = personality.get("traits", [])
            if traits:
                summary_parts.append(f"特质: {', '.join(str(t) for t in traits)}")
            if personality.get("manner"):
                summary_parts.append(f"举止: {personality.get('manner')}")
            if personality.get("motivation"):
                summary_parts.append(str(personality.get("motivation")))
            npc_doc = {
                "id": entity_id,
                "title": str(entity.get("name") or entity_id),
                "aliases": [str(a) for a in entity.get("aliases", [])],
                "summary": "；".join(summary_parts),
                "content": str(personality.get("motivation") or ""),
                "tags": entity_tags or ["npc"],
                "linked_entity_id": entity_id,
            }
            (world_dir / "characters" / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(npc_doc, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )


def _remove_world_dir(world_dir: Path) -> None:
    if world_dir.exists():
        shutil.rmtree(world_dir, ignore_errors=True)


def _build_exit_list(state) -> list[dict[str, str]]:
    return state.get_exits()


def _exit_movement_hints(state) -> list[str]:
    from diceflow.app.hints import exit_movement_hints
    return exit_movement_hints(state)


def _help_text() -> str:
    return (
        "回合动作（消耗回合）：直接输入你想做的事，例如：攻击守卫、检查左门、打开左门\n"
        "查看指令（不消耗回合）：look/看/观察、inv/背包、status/状态、hint/提示\n"
        "系统指令：q/quit/退出 结束游戏"
    )
