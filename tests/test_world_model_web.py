from __future__ import annotations

import unittest

from diceflow.scripting.loader import load_script
from diceflow.scripting.validation import validate_script
from diceflow.core.bootstrap import WorldBootstrap
from diceflow.core.state import GameState
from diceflow.world_model.schemas import get_favorability_config, get_time_config
from fastapi.testclient import TestClient
from diceflow.web.server import app


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


class BorderTownDemoConfigTest(unittest.TestCase):
    def test_script_exposes_custom_time_config(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        cfg = get_time_config(state)
        self.assertEqual(cfg["segments"], ["清晨", "正午", "黄昏", "深夜"])

    def test_script_exposes_custom_favorability_magnitude(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        cfg = get_favorability_config(state)
        self.assertEqual(cfg["magnitude_table"]["large"], 4)  # demo override
        self.assertTrue(any("lte" in r for r in cfg["thresholds"]))

    def test_state_starts_at_demo_clock(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        self.assertEqual(state.world_clock["segment"], "清晨")
        self.assertEqual(state.world_clock["day"], 1)


class WebWorldClockTest(unittest.TestCase):
    def test_status_exposes_world_clock(self) -> None:
        client = TestClient(app)
        sid = client.post("/api/sessions", json={"world_id": "border_town_tavern", "use_llm": False}).json()["session_id"]
        status = client.post(f"/api/sessions/{sid}/turns", json={"input": "等待", "forced_roll": 15}).json()["status"]
        self.assertIn("world_clock", status)
        self.assertEqual(status["world_clock"]["segment"], "正午")  # 清晨 +1

    def test_entity_record_has_relationship_history_count(self) -> None:
        client = TestClient(app)
        sid = client.post("/api/sessions", json={"world_id": "tomb_entrance", "use_llm": False}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "攻击守卫", "forced_roll": 15})
        status = client.get(f"/api/sessions/{sid}").json()["status"]
        guard = next(e for e in status["known_entities"] if e["id"] == "guard_1")
        self.assertEqual(guard.get("relationship_history_count"), 1)


if __name__ == "__main__":
    unittest.main()
