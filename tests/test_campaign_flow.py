from unittest.mock import patch

from diceflow.app.game import Game
from diceflow.scripting.loader import load_script
from diceflow.scripting.validation import validate_script


class FixedRoller:
    def randint(self, _low, _high):
        return 20


def _action(intent, target, target_id, text, tool="", tool_id=""):
    return {
        "intent_family": intent,
        "type": intent,
        "target": target,
        "target_id": target_id,
        "tool": tool,
        "tool_id": tool_id,
        "approach_tags": [],
        "method_text": text,
        "method": text,
    }


def _run(game, player_input, action):
    with patch("diceflow.app.game.parse_intent", return_value=action):
        return game.run_turn(player_input)


def test_campaign_script_loads_and_starts_in_town():
    script = load_script("border_town_campaign")

    validate_script(script)
    game = Game(script=script, use_llm=False)

    assert game.state.scene["id"] == "border_town_tavern"
    assert "barkeeper" in game.state.get_visible_entities()
    assert "road_to_tomb" in game.state.get_visible_entities()
    assert "guard_1" not in game.state.get_visible_entities()


def test_campaign_progresses_from_town_to_tomb_to_dungeon():
    game = Game(script=load_script("border_town_campaign"), use_llm=False)
    game.rules.rng = FixedRoller()

    town_record = _run(
        game,
        "前往古墓入口",
        _action("move", "古墓山道", "road_to_tomb", "前往古墓入口"),
    )

    assert town_record.validation["valid"] is True
    assert game.state.scene["id"] == "tomb_entrance"
    assert game.state.flags["campaign_stage"] == "tomb_entrance"
    assert "短剑" in game.state.player["inventory"]
    assert "火把" in game.state.player["inventory"]
    assert "guard_1" in game.state.get_visible_entities()
    assert "barkeeper" not in game.state.get_visible_entities()

    _run(game, "攻击守卫", _action("attack", "守卫", "guard_1", "攻击守卫"))
    kill_record = _run(game, "继续攻击守卫", _action("attack", "守卫", "guard_1", "继续攻击守卫"))
    assert kill_record.resolution_card is not None
    assert game.state.entities["guard_1"]["alive"] is False

    open_record = _run(game, "打开左门", _action("open", "左门", "left_door", "打开左门"))
    assert open_record.validation["valid"] is True
    assert game.state.flags["tomb_door_open"] is True
    assert "inner_passage" in game.state.get_visible_entities()

    dungeon_record = _run(
        game,
        "进入深处通道",
        _action("move", "深处通道", "inner_passage", "进入深处通道"),
    )

    assert dungeon_record.validation["valid"] is True
    assert game.state.scene["id"] == "dungeon_corridor"
    assert game.state.flags["campaign_stage"] == "dungeon_corridor"
    assert "skeleton_1" in game.state.get_visible_entities()
    assert "chest_1" in game.state.get_visible_entities()
    assert "iron_door" in game.state.get_visible_entities()
    assert "left_door" not in game.state.get_visible_entities()


def test_campaign_finishes_in_dungeon_after_key_and_iron_door():
    game = Game(script=load_script("border_town_campaign"), use_llm=False)
    game.rules.rng = FixedRoller()
    game.state.apply_changes(
        {
            "flags": {"campaign_stage": "dungeon_corridor", "entered_dungeon": True},
            "runtime_script_patch": {
                "id": "test_jump_to_dungeon",
                "ops": [
                    {
                        "op": "set_scene",
                        "scene": {
                            "id": "dungeon_corridor",
                            "name": "地牢走廊",
                            "description": "测试用地牢走廊。",
                        },
                    }
                ],
            },
            "set_entity_states": {
                "barkeeper": {"visible": False, "available": False},
                "notice_board": {"visible": False, "available": False},
                "road_to_tomb": {"visible": False, "available": False},
                "skeleton_1": {"visible": True, "available": True},
                "chest_1": {"visible": True, "available": True},
                "iron_door": {"visible": True, "available": True},
            },
        }
    )

    _run(game, "打开木箱", _action("open", "木箱", "chest_1", "打开木箱"))
    assert "iron_key" in game.state.get_visible_entities()

    _run(game, "拿起铁钥匙", _action("take", "铁钥匙", "iron_key", "拿起铁钥匙"))
    assert game.state.flags["has_key"] is True
    assert "铁钥匙" in game.state.player["inventory"]

    final_record = _run(
        game,
        "用铁钥匙打开铁门",
        _action("use", "铁门", "iron_door", "用铁钥匙打开铁门", tool="铁钥匙", tool_id="铁钥匙"),
    )

    assert final_record.validation["valid"] is True
    assert game.state.flags["final_door_open"] is True
    assert game.state.flags["game_over"] is True
    assert game.state.flags["ending"] == "victory"
