from __future__ import annotations

import unittest

from diceflow.scripting.loader import load_script
from diceflow.scripting.validation import validate_script


class ScriptWorldModelKeysTest(unittest.TestCase):
    def test_validate_accepts_world_model_and_world_clock(self) -> None:
        s = load_script("tomb_entrance")
        s["world_model"] = {"time": {"segments": ["dawn", "noon", "dusk"]}}
        s["world_clock"] = {"day": 2, "segment": "dusk", "weather": ""}
        validate_script(s)  # should not raise

    def test_validate_accepts_empty_world_model(self) -> None:
        s = load_script("tomb_entrance")
        s["world_model"] = {}
        s["world_clock"] = {}
        validate_script(s)


if __name__ == "__main__":
    unittest.main()
