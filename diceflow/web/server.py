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
