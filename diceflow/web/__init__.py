from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from diceflow.app.game import Game
from diceflow.core.bootstrap import WorldBootstrap, bootstrap_from_defaults, bootstrap_from_lorebook
from diceflow.core.lorebook import SessionLore
from diceflow.core.models import Thread
from diceflow.scripting.loader import load_script

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "sessions"


@dataclass
class Session:
    session_id: str
    script_id: str | None
    created_at: str
    updated_at: str
    game: Game = field(repr=False)
    turn_history: list[dict[str, Any]] = field(default_factory=list)
    lorebook: SessionLore = field(default_factory=SessionLore)
    display_name: str = ""
    use_llm: bool = True
    world_id: str | None = None
    bootstrap_data: dict[str, Any] | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "script_id": self.script_id,
            "world_id": self.world_id,
            "display_name": self.display_name or self.script_id or self.world_id or "unknown",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": len(self.turn_history),
            "ending": self._ending(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "script_id": self.script_id,
            "world_id": self.world_id,
            "display_name": self.display_name or self.script_id or self.world_id or "unknown",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "snapshot": self.game.state.get_snapshot(),
            "turn_history": self.turn_history,
            "is_game_over": bool(self.game.state.flags.get("game_over")),
            "ending": self.game.state.flags.get("ending"),
            "use_llm": self.use_llm,
            "bootstrap_data": self.bootstrap_data,
        }

    def _ending(self) -> str | None:
        return self.game.state.flags.get("ending")


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.data_dir = DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.load_from_disk()

    def create(
        self,
        script_id: str | None = None,
        world_id: str | None = None,
        use_llm: bool = True,
    ) -> Session:
        """Create a session from world content only.

        Legacy script_id-based sessions are no longer supported for new games.
        """
        session_id = uuid.uuid4().hex[:12]
        now = _now_iso()
        lorebook = SessionLore()
        if script_id:
            raise ValueError("script-driven sessions are no longer supported; use world_id")

        effective_world_id = world_id or "_default"
        bootstrap = bootstrap_from_lorebook(lorebook, effective_world_id) or bootstrap_from_defaults(effective_world_id)
        lorebook.seed_from_world_content_for_id(effective_world_id, bootstrap.entities)
        game = Game(script=bootstrap, use_llm=use_llm, lorebook=lorebook)
        display_name = bootstrap.title
        bootstrap_data = bootstrap.to_script_dict()

        session = Session(
            session_id=session_id,
            script_id=None,
            world_id=effective_world_id,
            display_name=display_name,
            created_at=now,
            updated_at=now,
            game=game,
            use_llm=use_llm,
            lorebook=lorebook,
            bootstrap_data=bootstrap_data,
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
            "world_id": session.world_id,
            "display_name": session.display_name or session.script_id or session.world_id or "unknown",
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "turn_history": session.turn_history,
            "snapshot": session.game.state.get_snapshot(),
            "lorebook": session.lorebook.to_dict(),
            "use_llm": session.use_llm,
            "bootstrap_data": session.bootstrap_data,
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
            script_id = record.get("script_id")
            world_id = record.get("world_id")
            display_name = record.get("display_name") or script_id or world_id or "unknown"
            lorebook = SessionLore.from_dict(record.get("lorebook"))
            session = Session(
                session_id=sid,
                script_id=script_id,
                world_id=world_id,
                display_name=display_name,
                created_at=record.get("created_at", ""),
                updated_at=record.get("updated_at", ""),
                game=_make_restored_game(
                    script_id=script_id,
                    world_id=world_id,
                    snapshot=record.get("snapshot"),
                    bootstrap_data=record.get("bootstrap_data"),
                    use_llm=bool(record.get("use_llm", True)),
                    lorebook=lorebook,
                ),
                turn_history=record.get("turn_history", []),
                lorebook=lorebook,
                use_llm=bool(record.get("use_llm", True)),
                bootstrap_data=record.get("bootstrap_data"),
            )
            self.sessions[sid] = session


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_restored_game(
    script_id: str | None = None,
    world_id: str | None = None,
    snapshot: object = None,
    bootstrap_data: dict[str, Any] | None = None,
    use_llm: bool = True,
    lorebook: Any = None,
) -> Game:
    """Restore a game from persistent data.

    Priority:
    1. script_id (legacy) — load from YAML script
    2. bootstrap_data — rebuild from stored bootstrap
    3. world_id — bootstrap from world content
    """
    if script_id:
        # Legacy: load from YAML script
        game = Game(script=load_script(script_id), use_llm=use_llm, lorebook=lorebook)
        if isinstance(snapshot, dict):
            _restore_snapshot_legacy(game, snapshot)
        return game

    if bootstrap_data:
        # Restore from stored bootstrap data
        bootstrap = WorldBootstrap(
            world_id=str(bootstrap_data.get("id") or ""),
            title=str(bootstrap_data.get("title", "")),
            intro=str(bootstrap_data.get("intro", "")),
            player=bootstrap_data.get("player", {}),
            scene=bootstrap_data.get("scene", {}),
            entities=bootstrap_data.get("entities", {}),
            flags=bootstrap_data.get("flags", {}),
            ending_conditions=bootstrap_data.get("ending_conditions", []),
            world=bootstrap_data.get("world"),
            scene_actions=bootstrap_data.get("scene_actions", {}),
            dynamic_entity_templates=bootstrap_data.get("dynamic_entity_templates", {}),
            generic_rules=bootstrap_data.get("generic_rules", []),
            action_rules=bootstrap_data.get("action_rules", []),
            dc_modifiers=bootstrap_data.get("dc_modifiers", []),
            derivation_rules=bootstrap_data.get("derivation_rules", []),
            reaction_rules=bootstrap_data.get("reaction_rules", []),
            runtime_generation_hooks=bootstrap_data.get("runtime_generation_hooks", []),
            invalid_action_event=str(bootstrap_data.get("invalid_action_event", "行动没有成立，但局势仍在推进。")),
            default_no_outcome_event=str(bootstrap_data.get("default_no_outcome_event", "局势发生了变化，你必须立刻决定下一步。")),
            ending_texts=bootstrap_data.get("ending_texts", {}),
        )
        game = Game(script=bootstrap, use_llm=use_llm, lorebook=lorebook)
        if isinstance(snapshot, dict):
            _restore_snapshot_bootstrap(game, snapshot)
        return game

    if world_id:
        lore = lorebook or SessionLore()
        bootstrap = bootstrap_from_lorebook(lore, world_id) or bootstrap_from_defaults(world_id)
        lore.seed_from_world_content_for_id(world_id, bootstrap.entities)
        game = Game(script=bootstrap, use_llm=use_llm, lorebook=lore)
        if isinstance(snapshot, dict):
            _restore_snapshot_bootstrap(game, snapshot)
        return game

    # Ultimate fallback
    bootstrap = bootstrap_from_defaults()
    game = Game(script=bootstrap, use_llm=use_llm, lorebook=lorebook)
    if isinstance(snapshot, dict):
        _restore_snapshot_bootstrap(game, snapshot)
    return game


def _restore_snapshot_legacy(game: Game, snapshot: dict[str, Any]) -> None:
    """Restore game state from a snapshot for legacy script-based sessions."""
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
    if "threads" in snapshot:
        threads = snapshot["threads"] if isinstance(snapshot["threads"], dict) else {}
        state.threads = {
            tid: Thread.from_dict(td) if isinstance(td, dict) else Thread(id=tid, title=tid)
            for tid, td in threads.items()
        }


def _restore_snapshot_bootstrap(game: Game, snapshot: dict[str, Any]) -> None:
    """Restore game state from a snapshot for bootstrap-based sessions."""
    state = game.state
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
    if "threads" in snapshot:
        threads = snapshot["threads"] if isinstance(snapshot["threads"], dict) else {}
        state.threads = {
            tid: Thread.from_dict(td) if isinstance(td, dict) else Thread(id=tid, title=tid)
            for tid, td in threads.items()
        }
