from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diceflow.app.game import Game
from diceflow.core.lorebook import SessionLore
from diceflow.scripting.loader import load_script

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sessions"


@dataclass
class Session:
    session_id: str
    script_id: str
    created_at: str
    updated_at: str
    game: Game = field(repr=False)
    turn_history: list[dict[str, Any]] = field(default_factory=list)
    lorebook: SessionLore = field(default_factory=SessionLore)
    display_name: str = ""
    use_llm: bool = True

    def to_summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "script_id": self.script_id,
            "display_name": self.display_name or self.script_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": len(self.turn_history),
            "ending": self._ending(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "script_id": self.script_id,
            "display_name": self.display_name or self.script_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "snapshot": self.game.state.get_snapshot(),
            "turn_history": self.turn_history,
            "is_game_over": bool(self.game.state.flags.get("game_over")),
            "ending": self.game.state.flags.get("ending"),
            "use_llm": self.use_llm,
        }

    def _ending(self) -> str | None:
        return self.game.state.flags.get("ending")


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.data_dir = DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.load_from_disk()

    def create(self, script_id: str, use_llm: bool = True) -> Session:
        session_id = uuid.uuid4().hex[:12]
        now = _now_iso()
        game = Game(script=load_script(script_id), use_llm=use_llm)
        script_title = str(game.script.get("title") or script_id)
        session = Session(
            session_id=session_id,
            script_id=script_id,
            display_name=script_title,
            created_at=now,
            updated_at=now,
            game=game,
            use_llm=use_llm,
        )
        self.sessions[session_id] = session
        self.save_to_disk(session)
        return session

    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        summaries = [s.to_summary() for s in self.sessions.values()]
        summaries.sort(key=lambda s: s["updated_at"], reverse=True)
        return summaries

    def delete(self, session_id: str) -> bool:
        if session_id not in self.sessions:
            return False
        del self.sessions[session_id]
        filepath = self.data_dir / f"{session_id}.json"
        try:
            filepath.unlink(missing_ok=True)
        except OSError:
            pass
        return True

    def save_to_disk(self, session: Session) -> None:
        session.updated_at = _now_iso()
        record = {
            "session_id": session.session_id,
            "script_id": session.script_id,
            "display_name": session.display_name or session.script_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "turn_history": session.turn_history,
            "snapshot": session.game.state.get_snapshot(),
            "lorebook": session.lorebook.to_dict(),
            "use_llm": session.use_llm,
        }
        filepath = self.data_dir / f"{session.session_id}.json"
        filepath.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_from_disk(self) -> None:
        if not self.data_dir.exists():
            return
        for filepath in sorted(self.data_dir.glob("*.json")):
            try:
                record = json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            sid = record.get("session_id")
            if not sid or sid in self.sessions:
                continue
            display_name = record.get("display_name") or record.get("script_id", "unknown")
            session = Session(
                session_id=sid,
                script_id=record.get("script_id", "unknown"),
                display_name=display_name,
                created_at=record.get("created_at", ""),
                updated_at=record.get("updated_at", ""),
                game=_make_restored_game(
                    record.get("script_id", "tomb_entrance"),
                    record.get("snapshot"),
                    bool(record.get("use_llm", True)),
                ),
                turn_history=record.get("turn_history", []),
                lorebook=SessionLore.from_dict(record.get("lorebook")),
                use_llm=bool(record.get("use_llm", True)),
            )
            self.sessions[sid] = session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_restored_game(script_id: str, snapshot: object, use_llm: bool) -> Game:
    game = Game(script=load_script(script_id), use_llm=use_llm)
    if isinstance(snapshot, dict):
        _restore_snapshot(game, snapshot)
    return game


def _restore_snapshot(game: Game, snapshot: dict[str, Any]) -> None:
    """Restore game state from a snapshot for continued play."""
    state = game.state
    state.script = load_script(game.script.get("id") or snapshot.get("script_id") or "")
    state.script_patches = []
    for patch in snapshot.get("script_patches", []):
        if isinstance(patch, dict):
            state.apply_script_patch(patch)
    state.turn_id = snapshot.get("turn_id", 0)
    if "player" in snapshot:
        state.player = snapshot["player"]
    if "scene" in snapshot:
        state.scene = snapshot["scene"]
    if "entities" in snapshot:
        state.entities = snapshot["entities"]
    if "flags" in snapshot:
        state.flags = snapshot["flags"]
    if "recent_events" in snapshot:
        state.recent_events = list(snapshot["recent_events"])
    if "entity_journal" in snapshot:
        state.entity_journal = list(snapshot["entity_journal"])
    if "history" in snapshot:
        state.history = list(snapshot["history"])
