import json
import unittest

from diceflow.app.game import Game
from diceflow.llm import heuristic_parse_intent, parse_intent
from diceflow.scripting.loader import load_script


class IntentParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        self.game.state.apply_changes({"player": {"inventory_add": ["铁钥匙"]}})

    def test_cautious_move_to_iron_door(self) -> None:
        action = heuristic_parse_intent(
            "往铁门移动，时刻保持警惕与低调",
            self.game.state,
        )

        self.assertEqual(action["intent_family"], "move")
        self.assertEqual(action["type"], "move")
        self.assertEqual(action["target"], "铁门")
        self.assertIn("careful", action["approach_tags"])

    def test_use_key_on_iron_door(self) -> None:
        action = heuristic_parse_intent(
            "低调地把铁钥匙插进锁孔，边听动静边拧动铁门",
            self.game.state,
        )

        self.assertEqual(action["intent_family"], "use")
        self.assertEqual(action["target"], "铁门")
        self.assertEqual(action["tool_id"], "铁钥匙")
        self.assertIn("careful", action["approach_tags"])

    def test_throw_chest_at_skeleton(self) -> None:
        action = heuristic_parse_intent("投掷木箱砸骷髅", self.game.state)

        self.assertEqual(action["intent_family"], "throw")
        self.assertEqual(action["target_id"], "skeleton_1")
        self.assertEqual(action["tool_id"], "chest_1")

    def test_open_use_interact_boundaries(self) -> None:
        examples = {
            "我拨弄箱子的锁扣": "open",
            "我试着打开箱子": "open",
            "我把钥匙插进门锁": "use",
            "我推动铁门": "open",
            "我摆弄机关": "interact",
        }

        for player_input, expected_family in examples.items():
            with self.subTest(player_input=player_input):
                action = heuristic_parse_intent(player_input, self.game.state)

                self.assertEqual(action["intent_family"], expected_family)

    def test_parse_intent_retries_llm_before_local_fallback(self) -> None:
        class FlakyLLM:
            def __init__(self) -> None:
                self.calls = 0

            def parse_intent(self, player_input, state):
                self.calls += 1
                if self.calls == 1:
                    raise json.JSONDecodeError("temporary", "", 0)
                return {
                    "intent_family": "wait",
                    "target": "",
                    "tool": "",
                    "approach_tags": [],
                    "method_text": player_input,
                }

        llm = FlakyLLM()

        action = parse_intent("等待", self.game.state, llm)

        self.assertEqual(action["intent_family"], "wait")
        self.assertEqual(llm.calls, 2)


if __name__ == "__main__":
    unittest.main()
