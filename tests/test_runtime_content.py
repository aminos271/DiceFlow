import random
import unittest
from copy import deepcopy
from unittest.mock import patch

from diceflow.app.game import Game
from diceflow.core.runtime_content import validate_runtime_patch
from diceflow.core.rules import RuleEngine
from diceflow.scripting.loader import load_script


class FakeRuntimeContentLLM:
    def __init__(self, patch: dict) -> None:
        self.patch = patch

    def generate_runtime_content(self, hook, action, check, state):
        return deepcopy(self.patch)


class RuntimeContentTest(unittest.TestCase):
    def test_standard_success_triggers_runtime_content_and_next_turn_uses_rules(self) -> None:
        script = load_script("tomb_entrance")
        script["scene_actions"]["inspect"] = {
            "dc": 5,
            "outcomes": {
                "success": {
                    "flags": {"scene_is_open": True},
                    "events": ["火把照亮了石门后的通道。"],
                }
            },
        }
        script["runtime_generation_hooks"] = [
            {
                "id": "dark_corridor_first_inspect",
                "when": {"intent_family": "inspect", "flags": {"scene_is_open": True}},
                "prompt_hint": "石门后的黑暗通道，火光照亮墙壁和地面。",
                "allowed_entity_types": ["pickup", "container", "npc"],
                "max_dc": 12,
            }
        ]
        patch_data = {
            "id": "dark_corridor_patch",
            "ops": [
                {
                    "op": "add_entity",
                    "id": "dyn_wall_inscription",
                    "entity": {
                        "name": "古代符文",
                        "aliases": ["符文"],
                        "type": "pickup",
                        "tags": ["dynamic", "clue"],
                        "metadata": {
                            "allowed_actions": ["inspect"],
                            "actions": {
                                "inspect": {
                                    "dc": 8,
                                    "outcomes": {
                                        "success": {
                                            "events": ["你辨认出符文像是在警告后来者。"]
                                        }
                                    },
                                }
                            },
                        },
                    },
                },
                {
                    "op": "add_entity",
                    "id": "dyn_bone_fragments",
                    "entity": {
                        "name": "碎骨",
                        "aliases": ["碎骨"],
                        "type": "container",
                        "tags": ["dynamic", "container"],
                    },
                },
                {
                    "op": "add_entity",
                    "id": "dyn_distant_sound",
                    "entity": {
                        "name": "远处微弱声响",
                        "aliases": ["声响"],
                        "type": "npc",
                        "tags": ["dynamic", "temporary"],
                        "metadata": {
                            "allowed_actions": ["inspect"],
                            "actions": {
                                "inspect": {
                                    "dc": 10,
                                    "outcomes": {
                                        "success": {
                                            "events": ["你分辨出声响来自通道深处。"]
                                        }
                                    },
                                }
                            },
                        },
                    },
                },
            ],
        }
        game = Game(script=script, use_llm=False)
        game.llm = FakeRuntimeContentLLM(patch_data)
        game.rules = RuleEngine(random.Random(0))
        first_action = {
            "intent_family": "inspect",
            "type": "inspect",
            "target": "",
            "target_id": "",
            "tool": "火把",
            "tool_id": "火把",
            "approach_tags": ["careful"],
            "method_text": "点燃火把仔细观察墙壁",
            "method": "点燃火把仔细观察墙壁",
        }

        with patch("diceflow.app.game.parse_intent", return_value=first_action):
            record = game.run_turn("点燃火把仔细观察墙壁")

        self.assertTrue(record.validation["valid"])
        self.assertTrue(game.state.flags["scene_is_open"])
        self.assertTrue(game.state.flags["generated.dark_corridor_first_inspect"])
        self.assertIn("runtime_script_patch", record.state_changes)
        self.assertEqual(len(game.state.script_patches), 1)
        for entity_id in ("dyn_wall_inscription", "dyn_bone_fragments", "dyn_distant_sound"):
            self.assertIn(entity_id, game.state.script["entities"])
            self.assertIn(entity_id, game.state.entities)

        inspect_rune = {
            "intent_family": "inspect",
            "type": "inspect",
            "target": "古代符文",
            "target_id": "dyn_wall_inscription",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "检查古代符文",
            "method": "检查古代符文",
        }
        game.rules = RuleEngine(random.Random(0))
        with patch("diceflow.app.game.parse_intent", return_value=inspect_rune):
            second = game.run_turn("检查古代符文")

        self.assertTrue(second.validation["valid"])
        self.assertNotEqual(second.validation["reason"], "dynamic_adjudication")
        self.assertFalse(second.check.get("dynamic", False))
        self.assertEqual(second.check["result"], "success")

    def test_runtime_content_validator_discards_unsafe_patch(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        hook = {
            "id": "unsafe_hook",
            "allowed_entity_types": ["pickup"],
            "max_dc": 10,
        }
        unsafe_patch = {
            "id": "unsafe_patch",
            "ops": [
                {
                    "op": "add_entity",
                    "id": "guard_1",
                    "entity": {
                        "name": "replacement",
                        "type": "pickup",
                    },
                },
                {"op": "set_flag", "key": "game_over", "value": True},
            ],
        }

        self.assertIsNone(validate_runtime_patch(unsafe_patch, hook, game.state))


if __name__ == "__main__":
    unittest.main()
