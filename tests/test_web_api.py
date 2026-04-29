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
        assert "known_entities" in status
        assert "hints" in status
        assert status["hp"] == 10
        assert status["max_hp"] == 10
        assert "短剑" in status["inventory"]

    def test_npc_entity_has_social_data(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        body = resp.json()
        entities = body["status"]["visible_entities"]
        guard = next((e for e in entities if e["id"] == "guard_1"), None)
        assert guard is not None
        assert guard.get("hostile") is True
        assert "disposition" in guard
        assert "favorability" in guard
        assert "personality" in guard


class TestKnownEntities:
    def test_hidden_entity_not_in_known_entities(self, isolated_store):
        """Hidden entities never discovered must not leak via known_entities."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        known = resp.json()["status"]["known_entities"]
        hidden_ids = {e["id"] for e in known}
        # guard_1_shield starts hidden and should NOT be known
        assert "guard_1_shield" not in hidden_ids, (
            "guard_1_shield is hidden at start and must not leak"
        )

    def test_visible_entity_in_known_entities(self, isolated_store):
        """Currently visible entities must appear in known_entities."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        known = resp.json()["status"]["known_entities"]
        guard = next((e for e in known if e["id"] == "guard_1"), None)
        assert guard is not None, "guard_1 is visible and must be in known_entities"
        assert guard["is_visible"] is True

    def test_inventory_items_in_known_entities(self, isolated_store):
        """Items in player inventory must appear in known_entities."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        known = resp.json()["status"]["known_entities"]
        inventory_ents = [e for e in known if e["is_in_inventory"]]
        assert len(inventory_ents) >= 1
        short_sword = next((e for e in inventory_ents if e["name"] == "短剑"), None)
        assert short_sword is not None
        assert short_sword["type"] == "item"

    def test_npc_in_known_entities_has_social_data(self, isolated_store):
        """NPC entities must carry social fields in known_entities."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        known = resp.json()["status"]["known_entities"]
        guard = next((e for e in known if e["id"] == "guard_1"), None)
        assert guard is not None
        assert guard.get("hostile") is True
        assert "disposition" in guard
        assert "favorability" in guard

    def test_known_entities_has_required_fields(self, isolated_store):
        """Every known_entities record must carry the canonical shape."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        known = resp.json()["status"]["known_entities"]
        assert len(known) > 0
        for ent in known:
            for field in ["id", "name", "type", "tags", "is_visible",
                          "is_in_inventory", "hostile", "locked", "opened",
                          "destroyed", "looted", "alive", "available",
                          "last_seen_turn_id"]:
                assert field in ent, f"Missing field '{field}' in entity {ent['id']}"

    def test_revealed_entity_appears_in_known_entities(self, isolated_store):
        """After an action reveals a hidden entity, it must show up."""
        data = _create_session(isolated_store, script_id="dungeon_corridor")
        sid = data["session_id"]

        # iron_key starts hidden — verify it is NOT known yet
        resp = client.get(f"/api/sessions/{sid}")
        known_ids = {e["id"] for e in resp.json()["status"]["known_entities"]}
        assert "iron_key" not in known_ids, "iron_key is hidden at start"

        # Open the chest to reveal iron_key
        resp = client.post(f"/api/sessions/{sid}/turns", json={"input": "打开木箱"})
        assert resp.status_code == 200, resp.text
        known = resp.json()["status"]["known_entities"]
        key = next((e for e in known if e["id"] == "iron_key"), None)
        assert key is not None, "iron_key must appear in known_entities after being revealed"
        assert key["name"] == "铁钥匙"

    def test_visible_count_matches_expected(self, isolated_store):
        """Sanity: known_entities visible subset == visible_entities count."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        body = resp.json()
        known = body["status"]["known_entities"]
        visible = body["status"]["visible_entities"]
        known_visible = [e for e in known if e["is_visible"]]
        assert len(known_visible) == len(visible)


class TestSessionUpdate:
    def test_update_display_name(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.patch(f"/api/sessions/{sid}", json={"display_name": "我的古墓冒险"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["display_name"] == "我的古墓冒险"

    def test_update_empty_name(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.patch(f"/api/sessions/{sid}", json={"display_name": "  "})
        assert resp.status_code == 422

    def test_update_too_long_name(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.patch(f"/api/sessions/{sid}", json={"display_name": "a" * 41})
        assert resp.status_code == 422

    def test_update_nonexistent_session(self):
        resp = client.patch("/api/sessions/deadbeef1234", json={"display_name": "test"})
        assert resp.status_code == 404

    def test_rename_persisted_to_disk(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        client.patch(f"/api/sessions/{sid}", json={"display_name": "改名测试"})
        filepath = isolated_store.data_dir / f"{sid}.json"
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        assert raw["display_name"] == "改名测试"

    def test_default_display_name_from_title(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        body = resp.json()
        assert body["display_name"] == "古墓入口"


class TestSessionDelete:
    def test_delete_session(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.delete(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert isolated_store.get(sid) is None

    def test_delete_session_via_post_fallback(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/delete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert isolated_store.get(sid) is None

    def test_delete_nonexistent_session(self, isolated_store):
        resp = client.delete("/api/sessions/deadbeef1234")
        assert resp.status_code == 404

    def test_delete_removes_disk_file(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        filepath = isolated_store.data_dir / f"{sid}.json"
        assert filepath.exists()
        client.delete(f"/api/sessions/{sid}")
        assert not filepath.exists()
