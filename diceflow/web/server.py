from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from diceflow.app.game import META_HELP, META_HINT, META_INV, META_LOOK, META_STATUS
from diceflow.scripting.loader import SCRIPT_DIR
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
    script_id: str
    use_llm: bool = True


class TurnRequest(BaseModel):
    input: str


class MetaRequest(BaseModel):
    command: str


class ScriptInfo(BaseModel):
    id: str
    title: str
    intro: str


class SessionSummary(BaseModel):
    session_id: str
    script_id: str
    display_name: str = ""
    created_at: str
    updated_at: str
    turn_count: int
    ending: str | None = None


class UpdateSessionRequest(BaseModel):
    display_name: str | None = None


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
    is_game_over: bool = False
    ending: str | None = None


# ── API Endpoints ─────────────────────────────────────────────────────

@app.get("/api/scripts")
def list_scripts() -> list[ScriptInfo]:
    scripts: list[ScriptInfo] = []
    for script_path in sorted(SCRIPT_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(script_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        if not isinstance(raw, dict):
            continue
        scripts.append(ScriptInfo(
            id=str(raw.get("id") or script_path.stem),
            title=str(raw.get("title") or script_path.stem),
            intro=str(raw.get("intro") or ""),
        ))
    return scripts


@app.post("/api/sessions")
def create_session(body: CreateSessionRequest) -> dict[str, Any]:
    script_path = SCRIPT_DIR / f"{body.script_id}.yaml"
    if not script_path.exists():
        raise HTTPException(status_code=404, detail=f"script not found: {body.script_id}")
    session = store.create(body.script_id, use_llm=body.use_llm)
    return {
        "session_id": session.session_id,
        "script_id": session.script_id,
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

    record = session.game.run_turn(body.input)
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
            })
            recorded_names.add(name)
            continue

        # Active entity in state.entities
        name = str(ent.get("name", eid))
        is_vis = eid in visible
        in_inv = name in inventory_names or ent.get("lifecycle", {}).get("phase") == "inventory"

        if is_vis:
            last_seen = state.turn_id
        else:
            je = journal_by_entity.get(eid)
            if je:
                last_seen = je.get("turn_id")
            else:
                last_seen = ent.get("lifecycle", {}).get("updated_turn_id")

        record: dict[str, Any] = {
            "id": eid,
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
        records.append(record)
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
        hints=state.get_available_action_hints() or ["检查周围", "等待/观察局势"],
        is_game_over=bool(state.flags.get("game_over")),
        ending=state.flags.get("ending"),
    )


def _help_text() -> str:
    return (
        "回合动作（消耗回合）：直接输入你想做的事，例如：攻击守卫、检查左门、打开左门\n"
        "查看指令（不消耗回合）：look/看/观察、inv/背包、status/状态、hint/提示\n"
        "系统指令：q/quit/退出 结束游戏"
    )
