import unittest

from diceflow.llm import heuristic_parse_intent


class IntentParserTest(unittest.TestCase):
    def test_cautious_move_to_iron_door(self) -> None:
        action = heuristic_parse_intent("\u5f80\u94c1\u95e8\u79fb\u52a8\uff0c\u65f6\u523b\u4fdd\u6301\u8b66\u60d5\u4e0e\u4f4e\u8c03")

        self.assertEqual(action["type"], "move")
        self.assertEqual(action["target"], "\u94c1\u95e8")


if __name__ == "__main__":
    unittest.main()

