from __future__ import annotations

import pytest

from diceflow.core.models import Location
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


@pytest.fixture
def fresh_state() -> GameState:
    return GameState(load_script("border_town_tavern"))


def test_add_location_creates_node(fresh_state: GameState):
    fresh_state.apply_changes({
        "add_location": {
            "cave_01": {
                "id": "cave_01",
                "name": "幽暗洞穴",
                "description": "一个黑暗的洞穴。",
                "discovered": True,
            },
        },
    })
    assert "cave_01" in fresh_state.locations
    loc = fresh_state.locations["cave_01"]
    assert loc.name == "幽暗洞穴"
    assert loc.description == "一个黑暗的洞穴。"
    assert loc.discovered is True


def test_add_location_duplicate_skipped(fresh_state: GameState):
    fresh_state.locations["cave_01"] = Location(id="cave_01", name="幽暗洞穴")
    fresh_state.apply_changes({
        "add_location": {
            "cave_01": {
                "id": "cave_01",
                "name": "不同的名字",
            },
        },
    })
    assert fresh_state.locations["cave_01"].name == "幽暗洞穴"


def test_update_location_adds_exits(fresh_state: GameState):
    fresh_state.locations["hall"] = Location(id="hall", name="大厅")
    fresh_state.locations["room"] = Location(id="room", name="房间")
    fresh_state.apply_changes({
        "update_location": {
            "hall": {"exits": {"北": "room"}},
        },
    })
    assert fresh_state.locations["hall"].exits == {"北": "room"}


def test_get_exits_returns_direction_and_name(fresh_state: GameState):
    fresh_state.scene["id"] = "current_id"
    fresh_state.locations["current_id"] = Location(
        id="current_id", name="当前地点",
        exits={"东": "market", "西": "tavern"},
    )
    fresh_state.locations["market"] = Location(id="market", name="集市")
    fresh_state.locations["tavern"] = Location(id="tavern", name="酒馆")
    exits = fresh_state.get_exits()
    assert len(exits) == 2
    directions = {e["direction"]: e["location_name"] for e in exits}
    assert directions["东"] == "集市"
    assert directions["西"] == "酒馆"


def test_current_scene_id_prefers_runtime_scene_over_world_id(fresh_state: GameState):
    fresh_state.script["id"] = "world_id"
    fresh_state.scene["id"] = "scene_a"
    assert fresh_state.get_current_scene_id() == "scene_a"

    fresh_state.flags["runtime.current_scene_id"] = "scene_b"
    assert fresh_state.get_current_scene_id() == "scene_b"


def test_get_exits_empty_when_no_current_location(fresh_state: GameState):
    fresh_state.scene["id"] = "nowhere"
    assert fresh_state.get_exits() == []


def test_location_snapshot_roundtrip(fresh_state: GameState):
    fresh_state.locations["room_a"] = Location(
        id="room_a", name="房间A", description="一个房间",
        discovered=True, danger_level=2,
        exits={"南": "room_b"},
        related_thread_ids=["thread_1"],
        last_visited_turn_id=5,
    )
    snapshot = fresh_state.get_snapshot()
    assert "locations" in snapshot
    assert "room_a" in snapshot["locations"]
    loc_data = snapshot["locations"]["room_a"]
    assert loc_data["name"] == "房间A"
    assert loc_data["exits"] == {"南": "room_b"}

    # Roundtrip
    new_state = GameState(load_script("border_town_tavern"))
    new_state.locations = {
        lid: Location.from_dict(ld) if isinstance(ld, dict) else Location(id=lid, name=lid)
        for lid, ld in snapshot["locations"].items()
    }
    assert new_state.locations["room_a"].name == "房间A"
    assert new_state.locations["room_a"].danger_level == 2
    assert new_state.locations["room_a"].exits == {"南": "room_b"}


def test_known_exit_match_detects_direction_text(fresh_state: GameState):
    from diceflow.core.dynamic_world import _match_known_exit

    fresh_state.scene["id"] = "current_id"
    fresh_state.locations["current_id"] = Location(
        id="current_id", name="当前地点",
        exits={"北": "north_room"},
    )
    fresh_state.locations["north_room"] = Location(id="north_room", name="北室")

    action = {"raw_input": "前往北", "method_text": "前往北", "method": "move", "target": ""}
    result = _match_known_exit(action, fresh_state)
    assert result == "north_room"

    # Also match by target location name
    action2 = {"raw_input": "走向北室", "method_text": "走向北室", "method": "move", "target": "北室"}
    result2 = _match_known_exit(action2, fresh_state)
    assert result2 == "north_room"


def test_known_exit_match_detects_location_name(fresh_state: GameState):
    from diceflow.core.dynamic_world import _match_known_exit

    fresh_state.scene["id"] = "current_id"
    fresh_state.locations["current_id"] = Location(
        id="current_id", name="当前地点",
        exits={"进入": "deep_cave"},
    )
    fresh_state.locations["deep_cave"] = Location(id="deep_cave", name="深处洞穴")

    action = {"raw_input": "我想去深处洞穴", "method_text": "进入深处洞穴", "method": "move", "target": "深处洞穴"}
    result = _match_known_exit(action, fresh_state)
    assert result == "deep_cave"


def test_known_exit_match_returns_none_for_unknown(fresh_state: GameState):
    from diceflow.core.dynamic_world import _match_known_exit

    fresh_state.scene["id"] = "current_id"
    fresh_state.locations["current_id"] = Location(
        id="current_id", name="当前地点",
        exits={"北": "north_room"},
    )
    fresh_state.locations["north_room"] = Location(id="north_room", name="北室")

    action = {"raw_input": "前往东", "method_text": "前往东", "method": "move", "target": ""}
    result = _match_known_exit(action, fresh_state)
    assert result is None


def test_dynamic_transition_records_origin_location_for_return(fresh_state: GameState):
    from diceflow.core.dynamic_world import dynamic_world_phase

    fresh_state.scene["id"] = "start_room"
    fresh_state.scene["name"] = "起点房间"
    fresh_state.scene["description"] = "这里是起点。"
    fresh_state.flags["scene_is_open"] = True
    fresh_state.script["world"] = {
        "premise": "test",
        "tone": "",
        "allowed_scene_types": ["room"],
        "allowed_entity_types": ["npc", "item"],
        "forbidden": [],
        "max_runtime_dc": 14,
        "max_new_entities_per_transition": 3,
    }

    class FakeLLM:
        def generate_dynamic_world(self, *_args, **_kwargs):
            return {
                "id": "patch_1",
                "source": "test",
                "turn_id": 1,
                "ops": [
                    {
                        "op": "set_scene",
                        "scene": {
                            "id": "deep_room",
                            "name": "深处房间",
                            "description": "这里更深。",
                        },
                    },
                    {"op": "set_flag", "key": "runtime.current_scene_id", "value": "deep_room"},
                ],
            }

    changes = dynamic_world_phase(
        {"type": "move", "raw_input": "进入北边房间", "method_text": "进入北边房间"},
        {"valid": False, "reason": "unknown"},
        fresh_state,
        FakeLLM(),
    )

    assert "start_room" in changes["add_location"]
    assert changes["add_location"]["start_room"]["name"] == "起点房间"
    assert changes["add_location"]["start_room"]["exits"]
    assert changes["add_location"]["deep_room"]["exits"]
