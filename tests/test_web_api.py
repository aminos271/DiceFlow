from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from diceflow.web import DATA_DIR, Session, SessionStore, _now_iso
from diceflow.web.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_store():
    """Run each test with a fresh, isolated in-memory SessionStore."""
    store = SessionStore()
    with tempfile.TemporaryDirectory() as tmpdir:
        store.data_dir = Path(tmpdir)
        store.sessions.clear()
        with mock.patch("diceflow.web.server.store", store):
            yield store


def _create_session(store, script_id="tomb_entrance", use_llm=False):
    resp = client.post("/api/sessions", json={"script_id": script_id, "use_llm": use_llm})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestListScripts:
    def test_list_scripts(self):
        resp = client.get("/api/scripts")
        assert resp.status_code == 200
        scripts = resp.json()
        assert isinstance(scripts, list)
        assert len(scripts) >= 1
        for s in scripts:
            assert "id" in s
            assert "title" in s
            assert "intro" in s


class TestCreateSession:
    def test_create_session(self, isolated_store):
        data = _create_session(isolated_store)
        assert "session_id" in data
        assert data["script_id"] == "tomb_entrance"
        assert "created_at" in data
        assert len(data["session_id"]) == 12

    def test_create_session_without_llm(self, isolated_store):
        data = _create_session(isolated_store, use_llm=False)
        assert "session_id" in data
        session = isolated_store.get(data["session_id"])
        assert session is not None
        assert session.game.llm is None

    def test_create_session_invalid_script(self, isolated_store):
        resp = client.post("/api/sessions", json={"script_id": "nonexistent_script"})
        assert resp.status_code == 404


class TestGetSession:
    def test_get_session(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        assert body["script_id"] == "tomb_entrance"
        assert "snapshot" in body
        assert "turn_history" in body
        assert "status" in body
        assert body["is_game_over"] is False

    def test_get_nonexistent_session(self, isolated_store):
        resp = client.get("/api/sessions/deadbeef1234")
        assert resp.status_code == 404


class TestListSessions:
    def test_list_sessions_empty(self, isolated_store):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_sessions_with_data(self, isolated_store):
        _create_session(isolated_store)
        _create_session(isolated_store, script_id="dungeon_corridor")
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 2
        for s in sessions:
            assert "session_id" in s
            assert "turn_count" in s
            assert "created_at" in s


class TestRunTurn:
    def test_run_turn(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "turn" in body
        assert "status" in body
        assert body["is_game_over"] in (True, False)
        turn = body["turn"]
        assert turn["player_input"] == "检查左门"
        assert "action" in turn
        assert "narration" in turn

    def test_run_turn_nonexistent_session(self, isolated_store):
        resp = client.post("/api/sessions/deadbeef1234/turns", json={"input": "检查"})
        assert resp.status_code == 404

    def test_run_multiple_turns(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        for i in range(3):
            resp = client.post(f"/api/sessions/{sid}/turns", json={"input": f"行动 {i}"})
            assert resp.status_code == 200, resp.text

        # Verify session has 3 turns in history
        session = isolated_store.get(sid)
        assert len(session.turn_history) == 3


class TestMetaCommands:
    def test_meta_look(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/meta", json={"command": "看"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "result" in body
        assert "status" in body

    def test_meta_inv(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/meta", json={"command": "背包"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "result" in body

    def test_meta_status(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/meta", json={"command": "status"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "status" in body

    def test_meta_hint(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/meta", json={"command": "hint"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "result" in body

    def test_meta_help(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/meta", json={"command": "help"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "帮助" in body["result"] or "指令" in body["result"]

    def test_meta_invalid(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/meta", json={"command": "nonexistent_cmd"})
        assert resp.status_code == 400

    def test_meta_nonexistent_session(self, isolated_store):
        resp = client.post("/api/sessions/deadbeef1234/meta", json={"command": "look"})
        assert resp.status_code == 404


class TestSessionPersistence:
    def test_session_persisted_to_disk(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Run a turn to trigger save
        client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})

        # Check file exists on disk
        filepath = isolated_store.data_dir / f"{sid}.json"
        assert filepath.exists()

        raw = json.loads(filepath.read_text(encoding="utf-8"))
        assert raw["session_id"] == sid
        assert raw["script_id"] == "tomb_entrance"
        assert len(raw["turn_history"]) == 1
        assert "snapshot" in raw

    def test_load_from_disk(self, isolated_store):
        # Create a session directly and save
        data = _create_session(isolated_store)
        sid = data["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})

        # Create a new store that loads from the same dir
        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        assert sid in store2.sessions
        loaded = store2.sessions[sid]
        assert loaded.script_id == "tomb_entrance"
        assert len(loaded.turn_history) == 1

    def test_loaded_session_can_continue(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})

        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        with mock.patch("diceflow.web.server.store", store2):
            resp = client.post(f"/api/sessions/{sid}/turns", json={"input": "等待"})

        assert resp.status_code == 200, resp.text
        assert len(store2.sessions[sid].turn_history) == 2
        assert resp.json()["status"]["turn_id"] == 2


class TestLLMKeySecurity:
    def test_llm_key_not_in_response(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Check session response
        resp = client.get(f"/api/sessions/{sid}")
        body = resp.json()
        _assert_no_key(body)

        # Check turn response
        resp = client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})
        body = resp.json()
        _assert_no_key(body)

        # Check scripts response
        resp = client.get("/api/scripts")
        body = resp.json()
        _assert_no_key(body)

        # Check sessions list
        resp = client.get("/api/sessions")
        body = resp.json()
        _assert_no_key(body)


def _assert_no_key(obj):
    """Recursively assert no API key strings appear in the response."""
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_no_key(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_no_key(v)
    elif isinstance(obj, str):
        assert "sk-" not in obj.lower(), f"Potential API key leak: {obj[:50]}"
        assert "deepseek" not in obj.lower() or "api" not in obj.lower(), f"Potential URL leak: {obj[:50]}"


class TestHealthCheck:
    def test_health(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestStatusData:
    def test_status_in_turn_response(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})
        body = resp.json()
        status = body["status"]
        assert "hp" in status
        assert "max_hp" in status
        assert "inventory" in status
        assert "scene_name" in status
        assert "scene_description" in status
        assert "visible_entities" in status
        assert "hints" in status
        assert status["hp"] == 10
        assert status["max_hp"] == 10
        assert "短剑" in status["inventory"]
