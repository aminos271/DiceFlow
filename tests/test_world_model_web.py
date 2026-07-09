from __future__ import annotations

import unittest

from diceflow.scripting.loader import load_script
from diceflow.scripting.validation import validate_script
from diceflow.core.bootstrap import WorldBootstrap


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


class WorldBootstrapPassThroughTest(unittest.TestCase):
    def test_to_script_dict_carries_world_model_and_clock(self) -> None:
        wb = WorldBootstrap(
            world_id="t", title="t",
            world_model={"time": {"segments": ["dawn", "dusk"]}},
            world_clock={"day": 2, "segment": "dusk", "weather": ""},
        )
        s = wb.to_script_dict()
        self.assertEqual(s["world_model"]["time"]["segments"], ["dawn", "dusk"])
        self.assertEqual(s["world_clock"]["day"], 2)

    def test_defaults_empty(self) -> None:
        s = WorldBootstrap(world_id="t", title="t").to_script_dict()
        self.assertEqual(s.get("world_model"), {})
        self.assertEqual(s.get("world_clock"), {})


if __name__ == "__main__":
    unittest.main()
