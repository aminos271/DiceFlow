import unittest

from diceflow.app.game import Game
from diceflow.llm import heuristic_parse_intent, parse_intent
from diceflow.scripting.loader import load_script


class IntentParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("dungeon_corridor"), use_llm=False)
        self.game.state.apply_changes({"player": {"inventory_add": ["\u94c1\u94a5\u5319"]}})

    def test_cautious_move_to_iron_door(self) -> None:
        action = heuristic_parse_intent(
            "\u5f80\u94c1\u95e8\u79fb\u52a8\uff0c\u65f6\u523b\u4fdd\u6301\u8b66\u60d5\u4e0e\u4f4e\u8c03",
            self.game.state,
        )

        self.assertEqual(action["intent_family"], "move")
        self.assertEqual(action["type"], "move")
        self.assertEqual(action["target"], "\u94c1\u95e8")
        self.assertIn("careful", action["approach_tags"])

    def test_use_key_on_iron_door(self) -> None:
        action = heuristic_parse_intent(
            "\u4f4e\u8c03\u5730\u628a\u94c1\u94a5\u5319\u63d2\u8fdb\u9501\u5b54\uff0c\u8fb9\u542c\u52a8\u9759\u8fb9\u62e7\u52a8\u94c1\u95e8",
            self.game.state,
        )

        self.assertEqual(action["intent_family"], "use")
        self.assertEqual(action["target"], "\u94c1\u95e8")
        self.assertEqual(action["tool_id"], "\u94c1\u94a5\u5319")
        self.assertIn("careful", action["approach_tags"])

    def test_open_use_interact_boundaries(self) -> None:
        examples = {
            "\u6211\u62e8\u5f04\u7bb1\u5b50\u7684\u9501\u6263": "open",
            "\u6211\u8bd5\u7740\u6253\u5f00\u7bb1\u5b50": "open",
            "\u6211\u628a\u94a5\u5319\u63d2\u8fdb\u95e8\u9501": "use",
            "\u6211\u63a8\u52a8\u94c1\u95e8": "open",
            "\u6211\u6446\u5f04\u673a\u5173": "interact",
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
                    raise RuntimeError("temporary")
                return {
                    "intent_family": "wait",
                    "target": "",
                    "tool": "",
                    "approach_tags": [],
                    "method_text": player_input,
                }

        llm = FlakyLLM()

        action = parse_intent("\u7b49\u5f85", self.game.state, llm)

        self.assertEqual(action["intent_family"], "wait")
        self.assertEqual(llm.calls, 2)


if __name__ == "__main__":
    unittest.main()
