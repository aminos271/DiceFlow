import random
import unittest
from copy import deepcopy
from unittest.mock import patch

from diceflow.app.game import Game
from diceflow.core.runtime_content import runtime_content_phase, validate_runtime_patch
from diceflow.core.rules import RuleEngine
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


class FakeRuntimeContentLLM:
    def __init__(self, patch: dict) -> None:
        self.patch = patch
        self.narration_available = True  # compat with narrate() duck-typing

    def generate_runtime_content(self, hook, action, check, state):
        return deepcopy(self.patch)


class RuntimeContentTest(unittest.TestCase):
    def test_runtime_content_phase_direct_call(self) -> None:
        """runtime_content_phase called directly — validates and returns patch.
        This tests the phase in isolation, since the default flow no longer calls it."""
        script = load_script("tomb_entrance")
        script["runtime_generation_hooks"] = [
            {
                "id": "test_hook",
                "when": {"intent_family": "inspect"},
                "prompt_hint": "测试提示。",
                "allowed_entity_types": ["pickup", "container"],
                "max_dc": 12,
            }
        ]
        state = GameState(script)
        state.flags["scene_is_open"] = True  # pre-set so the hook triggers
        check = {"dc": 5, "roll": 15, "result": "success"}
        action = {
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
        patch_data = {
            "id": "test_patch",
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
                                        "success": {"events": ["你辨认出符文像是在警告后来者。"]}
                                    },
                                }
                            },
                        },
                    },
                },
            ],
        }
        fake_llm = FakeRuntimeContentLLM(patch_data)

        changes = runtime_content_phase(action, check, {}, state, fake_llm)
        self.assertIsNotNone(changes.get("runtime_script_patch"))
        state.apply_changes(changes)
        self.assertIn("dyn_wall_inscription", state.entities)
        self.assertIn("dyn_wall_inscription", state.script["entities"])

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
