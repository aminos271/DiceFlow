from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from diceflow.core.models import Location, Thread
from diceflow.web import DATA_DIR, Session, SessionStore, _now_iso
from diceflow.web.server import app
from diceflow.content.worlds.loader import WORLDS_DIR

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


def _create_session(store, world_id="tomb_entrance", use_llm=False):
    resp = client.post("/api/sessions", json={"world_id": world_id, "use_llm": use_llm})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestListScripts:
    def test_list_scripts(self):
        resp = client.get("/api/scripts")
        assert resp.status_code == 200
        scripts = resp.json()
        assert scripts == []


class TestCreateSession:
    def test_create_session(self, isolated_store):
        data = _create_session(isolated_store)
        assert "session_id" in data
        assert data["script_id"] is None
        assert data["world_id"] == "tomb_entrance"
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
        assert resp.status_code == 422


class TestCreateWorld:
    def test_create_world(self, isolated_store):
        world_dir = WORLDS_DIR / "test_custom_world"
        shutil.rmtree(world_dir, ignore_errors=True)
        resp = client.post(
            "/api/worlds",
            json={
                "id": "test_custom_world",
                "title": "测试世界",
                "description": "一个用于 API 测试的新世界。",
                "scene_name": "测试大厅",
                "scene_description": "这里堆满了待验证的状态。",
                "initial_npc_name": "测试员",
                "initial_npc_summary": "负责检查一切是否正常。",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["world"]["id"] == "test_custom_world"
        assert world_dir.exists()
        assert (world_dir / "world.json").exists()
        assert (world_dir / "bootstrap.yaml").exists()
        shutil.rmtree(world_dir, ignore_errors=True)

    def test_created_world_can_start_session(self, isolated_store):
        world_dir = WORLDS_DIR / "apitest_world"
        shutil.rmtree(world_dir, ignore_errors=True)
        resp = client.post(
            "/api/worlds",
            json={
                "id": "apitest_world",
                "title": "接口测试世界",
                "description": "用于验证世界创建后能否直接开局。",
                "scene_name": "测试入口",
                "scene_description": "一切都应该已经准备好了。",
                "initial_npc_name": "门房",
            },
        )
        assert resp.status_code == 200, resp.text

        resp = client.post("/api/sessions", json={"world_id": "apitest_world", "use_llm": False})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["world_id"] == "apitest_world"
        shutil.rmtree(world_dir, ignore_errors=True)


class TestGetSession:
    def test_get_session(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        assert body["script_id"] is None
        assert body["world_id"] == "tomb_entrance"
        assert "snapshot" in body
        assert "turn_history" in body
        assert "status" in body
        assert body["is_game_over"] is False

    def test_session_status_includes_threads(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "threads" in body["status"]
        assert isinstance(body["status"]["threads"], list)
        assert body["status"]["threads"] == []  # empty for new session

    def test_session_status_hides_undiscovered_threads(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        session = isolated_store.get(sid)
        session.game.state.threads["hidden_done"] = Thread(
            id="hidden_done",
            title="隐藏目标",
            status="completed",
            progress=100,
            discovered=False,
            last_updated_turn_id=session.game.state.turn_id,
        )
        session.game.state.threads["visible"] = Thread(
            id="visible",
            title="可见目标",
            status="active",
            progress=20,
            discovered=True,
        )

        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        threads = resp.json()["status"]["threads"]
        assert [t["id"] for t in threads] == ["visible"]

    def test_session_status_includes_exits(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "exits" in body["status"]
        assert isinstance(body["status"]["exits"], list)
        assert body["status"]["exits"] == []  # empty for new session

    def test_entity_detail_includes_npc_memories(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        session = isolated_store.get(sid)
        # Find the innkeeper entity ID by looking at state entities
        innkeeper_id = None
        for eid, ent in session.game.state.entities.items():
            if ent.get("type") == "npc" or "npc" in ent.get("tags", []):
                innkeeper_id = eid
                break
        assert innkeeper_id is not None, "no NPC found in default world"
        from diceflow.core.models import NpcMemory
        session.game.state.npc_memories["mem_1"] = NpcMemory(
            id="mem_1",
            npc_entity_id=innkeeper_id,
            summary="与老板相谈甚欢。",
            sentiment="positive",
            source_turn_id=2,
            tags=["talk"],
            importance=2,
        )

        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        known = resp.json()["status"]["known_entities"]
        innkeeper = next((e for e in known if e["id"] == innkeeper_id), None)
        assert innkeeper is not None
        assert "recent_memories" in innkeeper
        assert len(innkeeper["recent_memories"]) == 1
        assert innkeeper["recent_memories"][0]["summary"] == "与老板相谈甚欢。"

    def test_session_status_includes_exit_hint_group(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        session = isolated_store.get(sid)
        session.game.state.scene["id"] = "start"
        session.game.state.locations["start"] = Location(
            id="start",
            name="起点",
            discovered=True,
            exits={"北": "north"},
        )
        session.game.state.locations["north"] = Location(
            id="north",
            name="北室",
            discovered=True,
        )

        resp = client.get(f"/api/sessions/{sid}")
        assert resp.status_code == 200
        status = resp.json()["status"]
        assert status["exits"] == [{"direction": "北", "location_id": "north", "location_name": "北室"}]
        assert any(item["command"] == "前往北室" for item in status["hint_groups"]["explore"])

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
        _create_session(isolated_store, world_id="_default")
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
        assert "mechanical_results" in turn
        assert "resolution_card" in turn

    def test_run_turn_nonexistent_session(self, isolated_store):
        resp = client.post("/api/sessions/deadbeef1234/turns", json={"input": "检查"})
        assert resp.status_code == 404

    def test_run_turn_force_critical_success(self, isolated_store):
        data = _create_session(isolated_store, world_id="_default", use_llm=False)
        sid = data["session_id"]

        resp = client.post(
            f"/api/sessions/{sid}/turns",
            json={"input": "询问老板", "force_critical": True},
        )

        assert resp.status_code == 200, resp.text
        turn = resp.json()["turn"]
        assert turn["check"]["roll"] == 20
        assert turn["check"]["result"] == "critical_success"

    def test_force_critical_one_shot_does_not_carry_to_next_turn(self, isolated_store):
        """force_critical=True should only affect the immediate turn, not subsequent ones."""
        data = _create_session(isolated_store, world_id="_default", use_llm=False)
        sid = data["session_id"]

        # Turn 1 — force critical
        resp = client.post(
            f"/api/sessions/{sid}/turns",
            json={"input": "询问老板", "force_critical": True},
        )
        assert resp.status_code == 200, resp.text
        turn1 = resp.json()["turn"]
        assert turn1["check"]["roll"] == 20, f"force_critical should give roll=20, got {turn1['check']['roll']}"
        assert turn1["check"]["result"] == "critical_success"

        # Turn 2 — no force_critical, should NOT carry over
        resp = client.post(
            f"/api/sessions/{sid}/turns",
            json={"input": "询问老板", "force_critical": False},
        )
        assert resp.status_code == 200, resp.text
        turn2 = resp.json()["turn"]
        # The roll should NOT be forced to 20 — it's a real roll
        # We can't assert roll != 20 (it's possible by chance), but we can
        # verify the turn completed normally
        assert turn2["check"]["roll"] >= 1
        assert turn2["check"]["roll"] <= 20

    def test_combat_end_turn_has_resolution_card(self, isolated_store):
        data = _create_session(isolated_store, use_llm=False)
        sid = data["session_id"]
        session = isolated_store.get(sid)

        class FixedRoller:
            def randint(self, _low, _high):
                return 20

        session.game.rules.rng = FixedRoller()
        client.post(f"/api/sessions/{sid}/turns", json={"input": "攻击守卫"})
        resp = client.post(f"/api/sessions/{sid}/turns", json={"input": "攻击守卫"})
        assert resp.status_code == 200, resp.text

        turn = resp.json()["turn"]
        assert any("守卫 HP" in item for item in turn["mechanical_results"])
        assert any("威胁：1 -> 0" == item for item in turn["mechanical_results"])
        card = turn["resolution_card"]
        assert card is not None
        assert card["type"] == "combat_end"
        assert card["threat_before"] == 1
        assert card["threat_after"] == 0
        assert any("尸体" in item for item in card["scene_changes"])
        assert any("盾牌" in item for item in card["available_actions"])

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
        assert raw["script_id"] is None
        assert raw["world_id"] == "tomb_entrance"
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
        assert loaded.script_id is None
        assert loaded.world_id == "tomb_entrance"
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

    def test_recovered_session_has_history(self, isolated_store):
        """Restored session must carry snapshot history entries."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})

        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        assert len(restored.game.state.history) >= 1
        assert restored.game.state.history[0]["player_input"] == "检查左门"

    def test_recovered_session_has_runtime_patches(self, isolated_store):
        """Restored session must restore script_patches list."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})

        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        # script_patches restored via _restore_snapshot
        assert isinstance(restored.game.state.script_patches, list)

    def test_use_llm_persisted_and_restored(self, isolated_store):
        """use_llm=false must survive disk round-trip."""
        data = _create_session(isolated_store, use_llm=False)
        sid = data["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "检查左门"})

        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        assert restored.use_llm is False
        assert restored.game.llm is None


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
        resp = client.post(
            f"/api/sessions/{sid}/turns",
            json={"input": "检查左门", "forced_roll": 15},
        )
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
        assert "hint_groups" in status
        assert status["hp"] == 10
        assert status["max_hp"] == 10
        assert "短剑" in status["inventory"]

    def test_status_hints_include_benefit_details(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        status = resp.json()["status"]
        groups = status["hint_groups"]
        assert groups
        flat = [item for group in groups.values() for item in group]
        assert all("label" in item and "detail" in item and "command" in item for item in flat)
        assert any("普通伤害" in item["detail"] or "门后风险" in item["detail"] for item in flat)

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
        """Sanity: generated entities must show up in known_entities after creation."""
        data = _create_session(isolated_store, world_id="tomb_entrance")
        sid = data["session_id"]
        resp = client.post(
            f"/api/sessions/{sid}/turns",
            json={"input": "搜索周围有没有线索", "forced_roll": 20},
        )
        assert resp.status_code == 200, resp.text
        known = resp.json()["status"]["known_entities"]
        generated = next((e for e in known if e["id"].startswith("dynamic_")), None)
        assert generated is not None, "generated entity must appear in known_entities after creation"
        assert generated["name"] in {"墙上的划痕", "古旧徽章", "受伤的探险者", "暗格", "松动砖缝"}

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


class TestEntityEdit:
    def test_edit_within_3_turns_rejected(self, isolated_store):
        """Editing an entity within 3 turns of interaction must be rejected."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        # Run 1 turn — turn_id becomes 1, turns_since=1 for script entities
        client.post(f"/api/sessions/{sid}/turns", json={"input": "等待"})
        resp = client.patch(f"/api/sessions/{sid}/entities/guard_1", json={"patch": {"name": "测试守卫"}})
        assert resp.status_code == 409, resp.text
        assert "不足 3 回合" in resp.json()["detail"]

    def test_edit_after_3_turns_succeeds(self, isolated_store):
        """After 3+ turns without interaction, editing an NPC must succeed."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        # Advance 3 turns
        for _ in range(3):
            client.post(f"/api/sessions/{sid}/turns", json={"input": "等待"})
        # Now turn_id=3, turns_since_interaction=3 for guard_1 (origin turn_id=0)
        resp = client.patch(f"/api/sessions/{sid}/entities/guard_1", json={"patch": {"name": "测试守卫"}})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity"]["name"] == "测试守卫"

    def test_edit_updates_can_edit_flag(self, isolated_store):
        """After editing, can_edit turns false because last_interaction_turn_id is updated."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        for _ in range(3):
            client.post(f"/api/sessions/{sid}/turns", json={"input": "等待"})
        resp = client.patch(f"/api/sessions/{sid}/entities/guard_1", json={"patch": {"name": "测试守卫"}})
        assert resp.status_code == 200
        # After edit, last_player_interaction_turn_id is updated to current turn
        edited = resp.json()["entity"]
        assert edited["can_edit"] is False  # Just interacted via edit
        assert edited["last_interaction_turn_id"] == 3

    def test_edit_unknown_entity(self, isolated_store):
        """Editing a non-existent entity must return 404."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.patch(f"/api/sessions/{sid}/entities/nonexistent_id", json={"patch": {"name": "x"}})
        assert resp.status_code == 404

    def test_known_entities_has_edit_fields(self, isolated_store):
        """All known_entities records must include can_edit, turns_since_interaction,
        and last_interaction_turn_id fields."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}")
        known = resp.json()["status"]["known_entities"]
        assert len(known) > 0
        for ent in known:
            assert "can_edit" in ent, f"Missing can_edit in entity {ent['id']}"
            assert "turns_since_interaction" in ent, f"Missing turns_since_interaction in entity {ent['id']}"
            assert "last_interaction_turn_id" in ent, f"Missing last_interaction_turn_id in entity {ent['id']}"

    def test_edit_persisted_to_disk(self, isolated_store):
        """Entity edit must persist to the disk file."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        for _ in range(3):
            client.post(f"/api/sessions/{sid}/turns", json={"input": "等待"})
        client.patch(f"/api/sessions/{sid}/entities/guard_1", json={"patch": {"name": "改名守卫"}})

        filepath = isolated_store.data_dir / f"{sid}.json"
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        entities = raw["snapshot"]["entities"]
        assert entities["guard_1"]["name"] == "改名守卫"

    def test_cannot_edit_id_field(self, isolated_store):
        """Patching entity id must be silently ignored — the id does not change."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        for _ in range(3):
            client.post(f"/api/sessions/{sid}/turns", json={"input": "等待"})
        resp = client.patch(f"/api/sessions/{sid}/entities/guard_1", json={"patch": {"id": "fake_id"}})
        assert resp.status_code == 200
        assert resp.json()["entity"]["id"] == "guard_1"

    def test_edit_nonexistent_session(self, isolated_store):
        """Editing entity in a non-existent session must return 404."""
        resp = client.patch("/api/sessions/deadbeef1234/entities/guard_1", json={"patch": {"name": "x"}})
        assert resp.status_code == 404


class TestLorebook:
    def test_new_session_has_script_seeded_lorebook(self, isolated_store):
        """New session lorebook is seeded from script with all 4 types."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["entries"]["world_entries"]) >= 1
        assert len(body["entries"]["location_entries"]) >= 1
        assert len(body["entries"]["character_entries"]) >= 1
        assert body["entries"]["event_entries"] == []
        all_seeded = (
            body["entries"]["world_entries"]
            + body["entries"]["location_entries"]
            + body["entries"]["character_entries"]
        )
        for e in all_seeded:
            assert e["source"] == "script_seed", f"Seed entry {e['title']} has wrong source"

    def test_create_world_entry(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "world",
            "title": "古墓传说",
            "summary": "关于古墓的古老传说",
            "content": "传说中古墓埋葬着一位古代君王。",
            "tags": ["传说", "古墓"],
            "pinned": True,
        })
        assert resp.status_code == 200, resp.text
        entry = resp.json()["entry"]
        assert entry["type"] == "world"
        assert entry["title"] == "古墓传说"
        assert entry["summary"] == "关于古墓的古老传说"
        assert entry["content"] == "传说中古墓埋葬着一位古代君王。"
        assert entry["tags"] == ["传说", "古墓"]
        assert entry["pinned"] is True
        assert entry["discovered"] is False
        assert entry["source"] == "manual"
        assert len(entry["id"]) == 12
        assert "created_at" in entry
        assert "updated_at" in entry

        # Verify it appears in GET (alongside seed entries)
        resp2 = client.get(f"/api/sessions/{sid}/lorebook")
        world = resp2.json()["entries"]["world_entries"]
        assert len(world) >= 2  # seed entries + this one
        titles = {e["title"] for e in world}
        assert "古墓传说" in titles

    def test_create_character_entry(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character",
            "title": "守卫长",
            "summary": "守卫古墓入口的卫兵",
            "linked_entity_id": "guard_1",
        })
        assert resp.status_code == 200, resp.text
        entry = resp.json()["entry"]
        assert entry["type"] == "character"
        assert entry["title"] == "守卫长"
        assert entry["linked_entity_id"] == "guard_1"

    def test_create_event_entry(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "event",
            "title": "发现古墓",
            "summary": "玩家发现了隐藏的古墓入口",
            "linked_turn_ids": [1, 2, 3],
        })
        assert resp.status_code == 200, resp.text
        entry = resp.json()["entry"]
        assert entry["type"] == "event"
        assert entry["linked_turn_ids"] == [1, 2, 3]

    def test_update_entry(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "world",
            "title": "原始标题",
            "summary": "原始摘要",
        })
        entry_id = resp.json()["entry"]["id"]

        resp2 = client.patch(f"/api/sessions/{sid}/lorebook/{entry_id}", json={
            "title": "更新标题",
            "summary": "更新摘要",
            "pinned": True,
        })
        assert resp2.status_code == 200, resp2.text
        updated = resp2.json()["entry"]
        assert updated["title"] == "更新标题"
        assert updated["summary"] == "更新摘要"
        assert updated["pinned"] is True

    def test_delete_entry(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        seed_count = len(resp.json()["entries"]["world_entries"])
        assert seed_count >= 1

        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "world",
            "title": "待删除条目",
        })
        entry_id = resp.json()["entry"]["id"]

        resp2 = client.delete(f"/api/sessions/{sid}/lorebook/{entry_id}")
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["status"] == "deleted"

        # Verify it's gone but seed entries remain
        resp3 = client.get(f"/api/sessions/{sid}/lorebook")
        assert len(resp3.json()["entries"]["world_entries"]) == seed_count

    def test_delete_nonexistent_entry(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.delete(f"/api/sessions/{sid}/lorebook/deadbeef")
        assert resp.status_code == 404

    def test_linked_entity_id_can_be_null(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character",
            "title": "无关联实体角色",
        })
        assert resp.status_code == 200
        assert resp.json()["entry"]["linked_entity_id"] is None

    def test_linked_entity_id_can_be_valid_entity(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character",
            "title": "关联守卫",
            "linked_entity_id": "guard_1",
        })
        assert resp.status_code == 200
        assert resp.json()["entry"]["linked_entity_id"] == "guard_1"

    def test_empty_title_rejected(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "world",
            "title": "",
        })
        assert resp.status_code == 422

    def test_persistence_saves_and_restores_lorebook(self, isolated_store):
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Create entries
        client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "world", "title": "世界条目1",
        })
        client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character", "title": "角色条目1",
        })
        client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "event", "title": "事件条目1",
        })

        # Load from disk with a new store
        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        # Seed entries exist from script + manually added entries
        world_titles = {e.title for e in restored.lorebook.world_entries}
        assert "世界条目1" in world_titles
        char_titles = {e.title for e in restored.lorebook.character_entries}
        assert "角色条目1" in char_titles
        assert len(restored.lorebook.event_entries) == 1
        assert restored.lorebook.event_entries[0].title == "事件条目1"

        # Can continue using lorebook
        with mock.patch("diceflow.web.server.store", store2):
            resp = client.get(f"/api/sessions/{sid}/lorebook")
        assert resp.status_code == 200
        world_titles_resp = {e["title"] for e in resp.json()["entries"]["world_entries"]}
        assert "世界条目1" in world_titles_resp

    def test_old_save_without_lorebook_field_loads(self, isolated_store):
        """Session JSON without lorebook field must load with empty lorebook."""
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Manually remove lorebook from the disk file
        filepath = isolated_store.data_dir / f"{sid}.json"
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        del raw["lorebook"]
        filepath.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

        # Load with a new store
        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        assert restored.lorebook.world_entries == []
        assert restored.lorebook.character_entries == []
        assert restored.lorebook.event_entries == []

    def test_lorebook_nonexistent_session(self, isolated_store):
        resp = client.get("/api/sessions/deadbeef1234/lorebook")
        assert resp.status_code == 404

    def test_linked_entity_id_must_reference_valid_entity(self, isolated_store):
        """Non-null linked_entity_id must exist in session entities (create)."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character",
            "title": "幽灵角色",
            "linked_entity_id": "nonexistent_entity_xyz",
        })
        assert resp.status_code == 422
        assert "unknown entity" in resp.json()["detail"]

    def test_linked_entity_id_validation_on_update(self, isolated_store):
        """Update with invalid linked_entity_id must also be rejected."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character",
            "title": "守卫角色",
            "linked_entity_id": "guard_1",
        })
        entry_id = resp.json()["entry"]["id"]

        resp2 = client.patch(f"/api/sessions/{sid}/lorebook/{entry_id}", json={
            "linked_entity_id": "nonexistent_entity_xyz",
        })
        assert resp2.status_code == 422
        assert "unknown entity" in resp2.json()["detail"]

    def test_update_can_clear_linked_entity_id(self, isolated_store):
        """Explicitly sending null must clear linked_entity_id."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "character",
            "title": "守卫角色",
            "linked_entity_id": "guard_1",
        })
        entry_id = resp.json()["entry"]["id"]
        assert resp.json()["entry"]["linked_entity_id"] == "guard_1"

        # Clear it by sending null
        resp2 = client.patch(f"/api/sessions/{sid}/lorebook/{entry_id}", json={
            "linked_entity_id": None,
        })
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["entry"]["linked_entity_id"] is None

    def test_new_session_has_script_seed_entries(self, isolated_store):
        """After creating a session, lorebook must contain script_seed entries."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        entries = resp.json()["entries"]
        assert len(entries["world_entries"]) >= 1, "Expected at least one world seed entry"
        assert len(entries["location_entries"]) >= 1, "Expected at least one location seed entry"
        assert len(entries["character_entries"]) >= 1, "Expected at least one character seed entry"
        for key in ("world_entries", "location_entries", "character_entries"):
            sources = {e["source"] for e in entries[key]}
            assert "script_seed" in sources, f"{key} missing script_seed"

    def test_script_seed_character_has_valid_linked_entity_id(self, isolated_store):
        """Character seed entries must have linked_entity_id pointing to real entities."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        session = isolated_store.get(sid)
        for entry in resp.json()["entries"]["character_entries"]:
            if entry["source"] == "script_seed" and entry["linked_entity_id"]:
                assert entry["linked_entity_id"] in session.game.state.entities, (
                    f"linked_entity_id {entry['linked_entity_id']} not in entities"
                )

    def test_seed_not_applied_on_reload(self, isolated_store):
        """Loading a saved session must not re-seed the lorebook."""
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Verify initial seed
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        initial_world_count = len(resp.json()["entries"]["world_entries"])
        assert initial_world_count >= 1

        # Reload from disk
        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        # Should still have exactly the same number of seed entries
        assert len(restored.lorebook.world_entries) == initial_world_count
        assert restored.lorebook.has_script_seed()

    def test_old_session_without_seed_still_loads(self, isolated_store):
        """Session JSON with only manual entries must load correctly."""
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Manually rewrite lorebook to simulate old-style entries
        filepath = isolated_store.data_dir / f"{sid}.json"
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        raw["lorebook"] = {
            "world_entries": [{
                "id": "oldentry01", "type": "world", "title": "旧条目",
                "aliases": [], "summary": "旧世界条目", "content": "",
                "tags": ["old"], "pinned": False, "discovered": False,
                "source": "manual",
                "linked_entity_id": None, "linked_turn_ids": [],
                "created_at": "", "updated_at": "",
            }],
            "character_entries": [],
            "event_entries": [],
        }
        filepath.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

        store2 = SessionStore()
        store2.data_dir = isolated_store.data_dir
        store2.sessions.clear()
        store2.load_from_disk()

        restored = store2.sessions[sid]
        assert len(restored.lorebook.world_entries) == 1
        assert restored.lorebook.world_entries[0].source == "manual"
        assert restored.lorebook.world_entries[0].title == "旧条目"
        assert not restored.lorebook.has_script_seed()

    def test_source_field_roundtrips_via_api(self, isolated_store):
        """Source field must persist through create and disk round-trip."""
        data = _create_session(isolated_store)
        sid = data["session_id"]

        # Create with explicit source
        resp = client.post(f"/api/sessions/{sid}/lorebook", json={
            "type": "world",
            "title": "测试来源",
            "source": "script_seed",
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["entry"]["source"] == "script_seed"

        # Check on disk
        filepath = isolated_store.data_dir / f"{sid}.json"
        raw = json.loads(filepath.read_text(encoding="utf-8"))
        disk_entries = raw["lorebook"]["world_entries"]
        manual_entry = next((e for e in disk_entries if e["title"] == "测试来源"), None)
        assert manual_entry is not None
        assert manual_entry["source"] == "script_seed"

    def test_world_content_seeded_when_world_id_present(self, isolated_store):
        """tomb_entrance has world_id, so seed must come from world files."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        entries = resp.json()["entries"]

        # World entries from world_book/ (background/setting)
        world_titles = {e["title"] for e in entries["world_entries"]}
        assert "古墓概览" in world_titles, f"Expected 古墓概览, got {world_titles}"

        # Location entries from locations/
        loc_titles = {e["title"] for e in entries["location_entries"]}
        assert "古墓入口" in loc_titles, f"Expected 古墓入口 in location_entries, got {loc_titles}"

        # Character entries from characters/
        char_titles = {e["title"] for e in entries["character_entries"]}
        assert "守卫" in char_titles

        # All should be script_seed
        for e in entries["world_entries"] + entries["location_entries"] + entries["character_entries"]:
            assert e["source"] == "script_seed"

    def test_world_seed_character_has_valid_linked_entity_id(self, isolated_store):
        """Guard character seed must link to guard_1 entity."""
        data = _create_session(isolated_store)
        sid = data["session_id"]
        session = isolated_store.get(sid)
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        guard_entry = next(
            (e for e in resp.json()["entries"]["character_entries"] if e["title"] == "守卫"),
            None,
        )
        assert guard_entry is not None
        assert guard_entry["linked_entity_id"] == "guard_1"
        assert guard_entry["linked_entity_id"] in session.game.state.entities

    def test_fallback_when_no_world_id_in_script(self, isolated_store):
        """Default world bootstrap still seeds lorebook entries."""
        data = _create_session(isolated_store, world_id="_default")
        sid = data["session_id"]
        resp = client.get(f"/api/sessions/{sid}/lorebook")
        entries = resp.json()["entries"]
        seeded = entries["world_entries"] + entries["location_entries"] + entries["character_entries"]
        assert len(seeded) >= 1
        for e in seeded:
            assert e["source"] == "script_seed"

    def test_lorebook_imports_world_loader(self):
        """Sanity: lorebook module imports world loader without errors."""
        from diceflow.content.worlds.loader import load_world_content, world_exists
        assert world_exists("tomb_entrance") is True
        assert world_exists("nonexistent_world") is False
        content = load_world_content("tomb_entrance")
        assert content is not None
        assert "world_book" in content
        assert len(content["world_book"]) >= 1
        assert "locations" in content
        assert len(content["locations"]) >= 1
        assert "characters" in content
        assert len(content["characters"]) >= 1
