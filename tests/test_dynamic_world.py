import unittest
from copy import deepcopy
from unittest.mock import patch

from diceflow.app.game import Game
from diceflow.scripting.loader import load_script


class FakeDynamicWorldLLM:
    def __init__(self, patch: dict) -> None:
        self.patch = patch

    def generate_dynamic_world(self, world, action, validation, state):
        return deepcopy(self.patch)


class DynamicWorldTest(unittest.TestCase):
    def test_invalid_move_through_open_door_generates_runtime_scene(self) -> None:
        script = load_script("tomb_entrance")
        script["world"] = {
            "premise": "古墓入口及其后方未知墓道",
            "tone": "潮湿、黑暗、古代机关、低魔",
            "allowed_scene_types": ["corridor", "chamber"],
            "allowed_entity_types": ["pickup", "container", "npc", "obstacle"],
            "forbidden": ["神器", "直接通关出口"],
            "max_runtime_dc": 12,
            "max_new_entities_per_transition": 3,
        }
        patch_data = {
            "id": "inner_corridor_patch",
            "ops": [
                {
                    "op": "set_scene",
                    "scene": {
                        "id": "dyn_inner_corridor",
                        "name": "黑暗通道",
                        "description": "石门后是一段潮湿狭窄的墓道，火把照亮墙壁上的刻痕。",
                    },
                },
                {"op": "set_flag", "key": "runtime.current_scene_id", "value": "dyn_inner_corridor"},
                {"op": "set_flag", "key": "generated.dyn_inner_corridor", "value": True},
                {
                    "op": "add_scene_action",
                    "action": "inspect",
                    "spec": {
                        "dc": 9,
                        "outcomes": {
                            "success": {"events": ["你借着火光看清通道墙壁和地面的痕迹。"]},
                            "fail": {"events": ["黑暗和潮气干扰了你的判断。"]},
                        },
                    },
                },
                {
                    "op": "add_entity",
                    "id": "dyn_wall_inscription",
                    "entity": {
                        "name": "墙壁符文",
                        "aliases": ["符文"],
                        "type": "pickup",
                        "tags": ["dynamic", "clue"],
                        "metadata": {
                            "allowed_actions": ["inspect"],
                            "actions": {
                                "inspect": {
                                    "dc": 8,
                                    "outcomes": {
                                        "success": {"events": ["你看出符文像是在警告后来者。"]}
                                    },
                                }
                            },
                        },
                    },
                },
            ],
        }
        game = Game(script=script, use_llm=False)
        game.llm = FakeDynamicWorldLLM(patch_data)
        game.state.apply_changes(
            {
                "entities": {
                    "guard_1": {"hp_delta": -6},
                    "left_door": {"opened": True, "locked": False},
                },
            }
        )
        action = {
            "intent_family": "move",
            "type": "move",
            "target": "内部",
            "target_id": "",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "进入内部",
            "method": "进入内部",
        }

        with patch("diceflow.app.game.parse_intent", return_value=action):
            record = game.run_turn("进入内部")

        self.assertEqual(record.validation["reason"], "dynamic_world")
        self.assertEqual(record.check["assessment"]["intent_kind"], "transition")
        self.assertEqual(game.state.scene["id"], "dyn_inner_corridor")
        self.assertEqual(game.state.flags["runtime.current_scene_id"], "dyn_inner_corridor")
        self.assertIn("inspect", game.state.script["scene_actions"])
        self.assertIn("dyn_wall_inscription", game.state.script["entities"])
        self.assertIn("dyn_wall_inscription", game.state.entities)
        self.assertFalse(game.state.entities["guard_1"]["alive"])

    def test_invalid_move_without_world_contract_falls_back_to_dynamic_adjudication(self) -> None:
        game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        game.state.apply_changes({"flags": {"door_open": True}})
        action = {
            "intent_family": "move",
            "type": "move",
            "target": "内部",
            "target_id": "",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "进入内部",
            "method": "进入内部",
        }

        with patch("diceflow.app.game.parse_intent", return_value=action):
            record = game.run_turn("进入内部")

        self.assertNotEqual(record.validation["reason"], "dynamic_world")


if __name__ == "__main__":
    unittest.main()
