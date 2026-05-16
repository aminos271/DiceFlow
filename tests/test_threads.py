from __future__ import annotations

import pytest

from diceflow.core.models import Thread
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


@pytest.fixture
def fresh_state() -> GameState:
    return GameState(load_script("border_town_tavern"))


class TestThreadDataclass:
    def test_thread_to_dict_and_from_dict_roundtrip(self) -> None:
        t = Thread(
            id="thread_1",
            title="调查失踪商队",
            status="active",
            progress=30,
            related_entity_ids=["entity_a", "entity_b"],
            related_location_ids=["location_x"],
            discovered=True,
            last_updated_turn_id=5,
            next_hint="去酒馆打听消息",
        )
        d = t.to_dict()
        restored = Thread.from_dict(d)
        assert restored.id == t.id
        assert restored.title == t.title
        assert restored.status == t.status
        assert restored.progress == t.progress
        assert restored.related_entity_ids == t.related_entity_ids
        assert restored.related_location_ids == t.related_location_ids
        assert restored.discovered is True
        assert restored.last_updated_turn_id == t.last_updated_turn_id
        assert restored.next_hint == t.next_hint

    def test_thread_from_dict_defaults(self) -> None:
        t = Thread.from_dict({"id": "t1", "title": "test"})
        assert t.status == "active"
        assert t.progress == 0
        assert t.discovered is False
        assert t.last_updated_turn_id == 0
        assert t.next_hint is None

    def test_thread_from_dict_sanitizes_invalid_values(self) -> None:
        t = Thread.from_dict({
            "id": "t1",
            "title": "test",
            "status": "bad",
            "progress": "not-number",
            "related_entity_ids": "not-list",
            "last_updated_turn_id": "bad",
            "next_hint": 123,
        })
        assert t.status == "active"
        assert t.progress == 0
        assert t.related_entity_ids == []
        assert t.last_updated_turn_id == 0
        assert t.next_hint == "123"


class TestThreadStateChanges:
    def test_add_thread_creates_thread(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "add_thread": {
                "quest_1": {
                    "id": "quest_1",
                    "title": "寻找钥匙",
                    "status": "active",
                    "progress": 0,
                    "discovered": True,
                    "next_hint": "检查木箱",
                }
            }
        })
        assert "quest_1" in fresh_state.threads
        t = fresh_state.threads["quest_1"]
        assert t.title == "寻找钥匙"
        assert t.status == "active"
        assert t.progress == 0
        assert t.discovered is True
        assert t.next_hint == "检查木箱"

    def test_add_thread_skips_duplicate(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(
            id="quest_1",
            title="原始标题",
            status="active",
            progress=10,
        )
        fresh_state.apply_changes({
            "add_thread": {
                "quest_1": {
                    "id": "quest_1",
                    "title": "新标题",
                    "status": "completed",
                    "progress": 100,
                }
            }
        })
        # Should not be overwritten
        assert fresh_state.threads["quest_1"].title == "原始标题"
        assert fresh_state.threads["quest_1"].status == "active"
        assert fresh_state.threads["quest_1"].progress == 10

    def test_update_thread_progress_delta(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试", progress=20)
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"progress_delta": 35}}
        })
        assert fresh_state.threads["quest_1"].progress == 55

    def test_update_thread_progress_clamps_to_100(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试", progress=90)
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"progress_delta": 30}}
        })
        assert fresh_state.threads["quest_1"].progress == 100

    def test_update_thread_progress_clamps_to_0(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试", progress=5)
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"progress_delta": -20}}
        })
        assert fresh_state.threads["quest_1"].progress == 0

    def test_update_thread_status_completed_auto_sets_progress(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试", progress=50)
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"status": "completed"}}
        })
        assert fresh_state.threads["quest_1"].status == "completed"
        assert fresh_state.threads["quest_1"].progress == 100

    def test_update_thread_sets_title(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="旧标题")
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"title": "新标题"}}
        })
        assert fresh_state.threads["quest_1"].title == "新标题"

    def test_update_thread_sets_discovered(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试", discovered=False)
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"discovered": True}}
        })
        assert fresh_state.threads["quest_1"].discovered is True

    def test_update_thread_appends_related_entity_ids(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(
            id="quest_1", title="测试", related_entity_ids=["e1"]
        )
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"related_entity_ids": ["e2", "e3"]}}
        })
        assert fresh_state.threads["quest_1"].related_entity_ids == ["e1", "e2", "e3"]

    def test_update_thread_related_entity_ids_deduplicates(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(
            id="quest_1", title="测试", related_entity_ids=["e1", "e2"]
        )
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"related_entity_ids": ["e2", "e3"]}}
        })
        assert fresh_state.threads["quest_1"].related_entity_ids == ["e1", "e2", "e3"]

    def test_update_thread_ignores_nonexistent_id(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "update_thread": {"nonexistent": {"progress_delta": 10}}
        })
        # Should not crash, just skip silently

    def test_update_thread_ignores_invalid_progress_delta(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试", progress=20)
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"progress_delta": "bad"}}
        })
        assert fresh_state.threads["quest_1"].progress == 20

    def test_add_thread_requires_title_after_sanitization(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "add_thread": {"quest_1": {"id": "quest_1", "progress": 20}}
        })
        assert "quest_1" not in fresh_state.threads

    def test_update_thread_last_updated_turn_id(self, fresh_state: GameState) -> None:
        fresh_state.turn_id = 5
        fresh_state.threads["quest_1"] = Thread(id="quest_1", title="测试")
        fresh_state.apply_changes({
            "update_thread": {"quest_1": {"progress_delta": 10}}
        })
        assert fresh_state.threads["quest_1"].last_updated_turn_id == 5


class TestThreadSnapshot:
    def test_threads_in_snapshot(self, fresh_state: GameState) -> None:
        fresh_state.threads["quest_1"] = Thread(
            id="quest_1",
            title="寻找钥匙",
            status="active",
            progress=50,
            discovered=True,
        )
        snapshot = fresh_state.get_snapshot()
        assert "threads" in snapshot
        assert "quest_1" in snapshot["threads"]
        assert snapshot["threads"]["quest_1"]["title"] == "寻找钥匙"
        assert snapshot["threads"]["quest_1"]["progress"] == 50

    def test_empty_threads_snapshot(self, fresh_state: GameState) -> None:
        snapshot = fresh_state.get_snapshot()
        assert "threads" in snapshot
        assert snapshot["threads"] == {}
