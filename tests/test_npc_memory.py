from __future__ import annotations

import pytest

from diceflow.core.models import NpcMemory
from diceflow.core.adjudicator import DynamicAdjudicator
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


@pytest.fixture
def fresh_state() -> GameState:
    return GameState(load_script("border_town_tavern"))


class TestNpcMemoryDataclass:
    def test_npc_memory_to_dict_and_from_dict_roundtrip(self) -> None:
        mem = NpcMemory(
            id="mem_1",
            npc_entity_id="innkeeper",
            summary="与旅店老板相谈甚欢。",
            sentiment="positive",
            source_turn_id=3,
            tags=["talk"],
            importance=2,
            discovered=True,
        )
        d = mem.to_dict()
        restored = NpcMemory.from_dict(d)
        assert restored.id == "mem_1"
        assert restored.npc_entity_id == "innkeeper"
        assert restored.summary == "与旅店老板相谈甚欢。"
        assert restored.sentiment == "positive"
        assert restored.source_turn_id == 3
        assert restored.tags == ["talk"]
        assert restored.importance == 2
        assert restored.discovered is True

    def test_npc_memory_from_dict_defaults(self) -> None:
        mem = NpcMemory.from_dict({"id": "m1", "npc_entity_id": "n1", "summary": "test"})
        assert mem.id == "m1"
        assert mem.npc_entity_id == "n1"
        assert mem.summary == "test"
        assert mem.sentiment == "neutral"
        assert mem.source_turn_id == 0
        assert mem.tags == []
        assert mem.importance == 1
        assert mem.discovered is True

    def test_npc_memory_from_dict_sanitizes_invalid_sentiment(self) -> None:
        mem = NpcMemory.from_dict({"id": "m1", "npc_entity_id": "n1", "sentiment": "bad"})
        assert mem.sentiment == "neutral"

    def test_npc_memory_from_dict_clamps_importance(self) -> None:
        mem_low = NpcMemory.from_dict({"id": "m1", "npc_entity_id": "n1", "importance": -5})
        assert mem_low.importance == 0
        mem_high = NpcMemory.from_dict({"id": "m2", "npc_entity_id": "n1", "importance": 99})
        assert mem_high.importance == 5


class TestNpcMemoryStateChanges:
    def test_add_npc_memory_creates_memory(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "add_npc_memory": {
                "mem_1": {
                    "npc_entity_id": "innkeeper",
                    "summary": "与旅店老板交谈。",
                    "sentiment": "positive",
                    "tags": ["talk"],
                },
            },
        })
        assert "mem_1" in fresh_state.npc_memories
        mem = fresh_state.npc_memories["mem_1"]
        assert mem.npc_entity_id == "innkeeper"
        assert mem.summary == "与旅店老板交谈。"
        assert mem.sentiment == "positive"

    def test_add_npc_memory_allows_multiple_same_npc(self, fresh_state: GameState) -> None:
        fresh_state.turn_id = 1
        fresh_state.apply_changes({
            "add_npc_memory": {
                "mem_talk": {
                    "npc_entity_id": "innkeeper",
                    "summary": "第一次交谈。",
                    "sentiment": "positive",
                },
            },
        })
        fresh_state.turn_id = 3
        fresh_state.apply_changes({
            "add_npc_memory": {
                "mem_talk": {
                    "npc_entity_id": "innkeeper",
                    "summary": "第二次交谈。",
                    "sentiment": "neutral",
                },
            },
        })
        assert "mem_talk" in fresh_state.npc_memories
        assert "mem_talk_3" in fresh_state.npc_memories
        assert fresh_state.npc_memories["mem_talk"].summary == "第一次交谈。"
        assert fresh_state.npc_memories["mem_talk_3"].summary == "第二次交谈。"

    def test_add_npc_memory_skips_empty_summary(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "add_npc_memory": {
                "mem_1": {
                    "npc_entity_id": "innkeeper",
                    "summary": "",
                },
            },
        })
        assert len(fresh_state.npc_memories) == 0

    def test_add_npc_memory_skips_empty_npc_entity_id(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "add_npc_memory": {
                "mem_1": {
                    "summary": "缺少 NPC 引用的记忆不应写入。",
                },
            },
        })
        assert len(fresh_state.npc_memories) == 0

    def test_update_npc_memory_modifies_fields(self, fresh_state: GameState) -> None:
        fresh_state.npc_memories["mem_1"] = NpcMemory(
            id="mem_1", npc_entity_id="innkeeper",
            summary="原始记忆。", sentiment="neutral",
        )
        fresh_state.apply_changes({
            "update_npc_memory": {
                "mem_1": {
                    "sentiment": "positive",
                    "importance": 3,
                    "tags": ["new_tag"],
                },
            },
        })
        assert fresh_state.npc_memories["mem_1"].sentiment == "positive"
        assert fresh_state.npc_memories["mem_1"].importance == 3
        assert "new_tag" in fresh_state.npc_memories["mem_1"].tags

    def test_update_npc_memory_ignores_nonexistent_id(self, fresh_state: GameState) -> None:
        fresh_state.apply_changes({
            "update_npc_memory": {
                "nonexistent": {"summary": "不会创建。"},
            },
        })
        assert "nonexistent" not in fresh_state.npc_memories


class TestNpcMemorySnapshot:
    def test_npc_memory_snapshot_roundtrip(self, fresh_state: GameState) -> None:
        fresh_state.npc_memories["mem_a"] = NpcMemory(
            id="mem_a", npc_entity_id="guard_1",
            summary="与守卫交谈。", sentiment="positive",
            source_turn_id=2, tags=["talk"], importance=1,
        )
        snapshot = fresh_state.get_snapshot()
        assert "npc_memories" in snapshot
        assert "mem_a" in snapshot["npc_memories"]

        new_state = GameState(load_script("border_town_tavern"))
        new_state.npc_memories = {
            mid: NpcMemory.from_dict(md) if isinstance(md, dict) else NpcMemory(id=mid, npc_entity_id="", summary="")
            for mid, md in snapshot["npc_memories"].items()
        }
        assert new_state.npc_memories["mem_a"].summary == "与守卫交谈。"
        assert new_state.npc_memories["mem_a"].sentiment == "positive"
        assert new_state.npc_memories["mem_a"].tags == ["talk"]

    def test_get_memories_for_npc_filters_and_sorts(self, fresh_state: GameState) -> None:
        fresh_state.npc_memories["mem_1"] = NpcMemory(
            id="mem_1", npc_entity_id="guard_1",
            summary="第一回合", source_turn_id=1,
        )
        fresh_state.npc_memories["mem_2"] = NpcMemory(
            id="mem_2", npc_entity_id="guard_1",
            summary="第三回合", source_turn_id=3,
        )
        fresh_state.npc_memories["mem_3"] = NpcMemory(
            id="mem_3", npc_entity_id="innkeeper",
            summary="第二回合", source_turn_id=2,
        )
        # Undiscovered memory should be excluded
        fresh_state.npc_memories["mem_hidden"] = NpcMemory(
            id="mem_hidden", npc_entity_id="guard_1",
            summary="隐藏", source_turn_id=4, discovered=False,
        )

        guard_memories = fresh_state.get_memories_for_npc("guard_1")
        assert len(guard_memories) == 2
        assert guard_memories[0]["summary"] == "第三回合"
        assert guard_memories[1]["summary"] == "第一回合"

        innkeeper_memories = fresh_state.get_memories_for_npc("innkeeper")
        assert len(innkeeper_memories) == 1
        assert innkeeper_memories[0]["summary"] == "第二回合"


class TestNpcMemoryAdjudication:
    def test_dynamic_failure_does_not_add_memory_for_non_npc_target(self) -> None:
        state = GameState(load_script("tomb_entrance"))
        adjudicator = DynamicAdjudicator()
        changes = adjudicator.update_state(
            {"target_id": "left_door", "target": "左门", "method_text": "威胁左门让它打开"},
            {
                "result": "fail",
                "assessment": {"intent_kind": "social", "risk": "medium"},
            },
            state,
        )
        assert "add_npc_memory" not in changes
