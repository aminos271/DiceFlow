from __future__ import annotations

from copy import deepcopy

import pytest

from diceflow.core.npc_autonomy import (
    _clamp_and_filter,
    _deterministic_autonomy,
    _eligible_npcs,
    _visible_npcs,
    npc_autonomy_phase,
    record_autonomy_turn,
)
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


def _make_state(script_name="tomb_entrance"):
    script = load_script(script_name)
    return GameState(script)


def _npc_state(**overrides):
    base = {
        "type": "npc",
        "name": "测试NPC",
        "hp": 5,
        "max_hp": 5,
        "alive": True,
        "visible": True,
        "available": True,
        "hostile": False,
        "favorability": 0,
        "disposition": "neutral",
        "personality": {"traits": ["冷静"], "manner": "平淡", "motivation": ""},
        "tags": ["npc"],
    }
    base.update(overrides)
    return base


class TestVisibleNpcs:
    def test_returns_npc_entities(self):
        state = _make_state()
        state.entities["test_npc"] = _npc_state()
        result = _visible_npcs(state)
        assert "test_npc" in result

    def test_excludes_non_npc(self):
        state = _make_state()
        state.entities["test_item"] = {"type": "item", "name": "剑", "visible": True, "available": True}
        result = _visible_npcs(state)
        assert "test_item" not in result

    def test_excludes_dead_npc(self):
        state = _make_state()
        state.entities["dead_npc"] = _npc_state(alive=False)
        result = _visible_npcs(state)
        assert "dead_npc" not in result

    def test_excludes_unavailable_npc(self):
        state = _make_state()
        state.entities["hidden_npc"] = _npc_state(available=False)
        result = _visible_npcs(state)
        assert "hidden_npc" not in result


class TestEligibleNpcs:
    def test_respects_cooldown(self):
        state = _make_state()
        state.turn_id = 5
        npc = _npc_state(last_autonomy_turn=4)
        state.entities["cool_npc"] = npc
        npcs = {"cool_npc": npc}
        action = {"intent_family": "inspect", "target": "left_door"}
        result = _eligible_npcs(npcs, action, state)
        assert "cool_npc" not in result  # last_autonomy_turn=4, turn_id=5, diff=1 < 2

    def test_allows_after_cooldown(self):
        state = _make_state()
        state.turn_id = 5
        npc = _npc_state(last_autonomy_turn=3)
        state.entities["cool_npc"] = npc
        npcs = {"cool_npc": npc}
        action = {"intent_family": "inspect", "target": "left_door"}
        result = _eligible_npcs(npcs, action, state)
        assert "cool_npc" in result

    def test_prioritizes_hostile(self):
        state = _make_state()
        state.turn_id = 5
        friendly = _npc_state(name="友善", favorability=3, disposition="friendly")
        hostile_npc = _npc_state(name="敌人", hostile=True, disposition="hostile")
        npcs = {"friendly_npc": friendly, "hostile_npc": hostile_npc}
        action = {"intent_family": "inspect", "target": "left_door"}
        result = _eligible_npcs(npcs, action, state)
        # Should only return the highest priority (hostile)
        assert len(result) == 1
        assert "hostile_npc" in result

    def test_excludes_directly_handled_target(self):
        state = _make_state()
        state.turn_id = 5
        hostile_npc = _npc_state(name="敌人", hostile=True, disposition="hostile")
        npcs = {"hostile_npc": hostile_npc}
        action = {"intent_family": "attack", "target_id": "hostile_npc"}
        result = _eligible_npcs(npcs, action, state)
        assert result == {}


class TestDeterministicAutonomy:
    def test_hostile_npc_pressures(self):
        state = _make_state()
        state.player["hp"] = 8
        npcs = {"bad_guy": _npc_state(name="敌人", hostile=True, disposition="hostile", tags=["npc", "hostile"])}
        action = {"intent_family": "inspect", "target": "left_door"}
        result = _deterministic_autonomy(npcs, action, state)
        changes = result.get("changes", {})
        assert changes.get("player", {}).get("hp_delta") == -1
        assert len(changes.get("events", [])) > 0

    def test_hostile_npc_does_not_kill(self):
        state = _make_state()
        state.player["hp"] = 1
        npcs = {"bad_guy": _npc_state(name="敌人", hostile=True, disposition="hostile", tags=["npc", "hostile"])}
        action = {"intent_family": "wait"}
        result = _deterministic_autonomy(npcs, action, state)
        changes = result.get("changes", {})
        player_changes = changes.get("player", {})
        # With hp=1, the deterministic should not add damage
        assert player_changes.get("hp_delta", 0) >= 0

    def test_friendly_npc_gives_hint(self):
        state = _make_state()
        npcs = {"friend": _npc_state(name="朋友", favorability=3, disposition="friendly")}
        action = {"intent_family": "inspect", "target": "left_door"}
        result = _deterministic_autonomy(npcs, action, state)
        changes = result.get("changes", {})
        assert "player" not in changes  # No damage
        assert len(changes.get("events", [])) > 0

    def test_suspicious_npc_is_cold(self):
        state = _make_state()
        npcs = {"cold_guy": _npc_state(name="冷淡的人", favorability=-2, disposition="suspicious")}
        action = {"intent_family": "talk", "target_id": "cold_guy"}
        result = _deterministic_autonomy(npcs, action, state)
        changes = result.get("changes", {})
        assert changes.get("entities", {}).get("cold_guy", {}).get("favorability_delta") == -1


class TestNpcAutonomyPhase:
    def test_skips_when_game_over(self):
        state = _make_state()
        state.flags["game_over"] = True
        action = {"intent_family": "inspect", "target": "left_door"}
        result = npc_autonomy_phase(action, None, {}, state, None)
        assert result == {}

    def test_skips_when_player_dead(self):
        state = _make_state()
        state.player["hp"] = 0
        action = {"intent_family": "inspect", "target": "left_door"}
        result = npc_autonomy_phase(action, None, {}, state, None)
        assert result == {}

    def test_returns_valid_state_changes_no_llm(self):
        state = _make_state()
        state.entities["guard_1"]["last_autonomy_turn"] = 0  # Allow autonomy
        action = {"intent_family": "wait"}
        result = npc_autonomy_phase(action, None, {}, state, None)
        assert "events" in result or result == {}

    def test_records_actor_cooldown_even_for_event_only_action(self):
        state = _make_state()
        state.turn_id = 5
        state.entities["guard_1"]["available"] = False
        state.entities["friend"] = _npc_state(name="朋友", favorability=3, disposition="friendly")
        action = {"intent_family": "wait"}
        result = npc_autonomy_phase(action, None, {}, state, None)
        assert result["set_entity_states"]["friend"]["last_autonomy_turn"] == 5

    def test_autonomy_in_tomb_entrance(self):
        """Integration: guard_1 should act when player waits."""
        state = _make_state()
        state.entities["guard_1"]["last_autonomy_turn"] = 0
        action = {"intent_family": "wait"}
        result = npc_autonomy_phase(action, None, {}, state, None)
        # guard_1 is hostile, should produce at minimum events
        assert isinstance(result, dict)
        if result:
            assert "events" in result or "player" in result


class TestClampAndFilter:
    def test_clamps_player_hp_delta(self):
        result = {"actor_id": "npc1", "changes": {"player": {"hp_delta": -5}}}
        state = _make_state()
        state.player["hp"] = 5
        changes = _clamp_and_filter(result, state)
        assert changes["player"]["hp_delta"] == -1

    def test_prevents_lethal_damage(self):
        result = {"actor_id": "npc1", "changes": {"player": {"hp_delta": -1}}}
        state = _make_state()
        state.player["hp"] = 1
        changes = _clamp_and_filter(result, state)
        assert changes["player"]["hp_delta"] == 0

    def test_clamps_favorability_delta(self):
        result = {"actor_id": "npc1", "changes": {"entities": {"npc1": {"favorability_delta": 5}}}}
        state = _make_state()
        state.entities["npc1"] = _npc_state()
        changes = _clamp_and_filter(result, state)
        assert changes["entities"]["npc1"]["favorability_delta"] == 1

    def test_strips_forbidden_keys(self):
        result = {
            "actor_id": "npc1",
            "changes": {
                "events": ["test"],
                "spawn_entities": {"bad": {}},
                "remove_entities": ["bad"],
            },
        }
        state = _make_state()
        changes = _clamp_and_filter(result, state)
        assert "spawn_entities" not in changes
        assert "remove_entities" not in changes
        assert "events" in changes


class TestRecordAutonomyTurn:
    def test_sets_last_autonomy_turn(self):
        state = _make_state()
        state.turn_id = 5
        state.entities["guard_1"]["last_autonomy_turn"] = 0
        changes = {"entities": {"guard_1": {"favorability_delta": -1}}}
        record_autonomy_turn(state, changes)
        assert state.entities["guard_1"]["last_autonomy_turn"] == 5
