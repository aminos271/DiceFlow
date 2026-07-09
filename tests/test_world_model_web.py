from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diceflow.web
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


class WorldModelPersistenceTest(unittest.TestCase):
    def test_world_clock_and_config_survive_reload(self) -> None:
        tmp = tempfile.mkdtemp()
        try:
            with patch.object(diceflow.web, "DATA_DIR", Path(tmp)):
                store = diceflow.web.SessionStore()
                sess = store.create(world_id="border_town_tavern", use_llm=False)
                sess.game.state.apply_changes({"advance_time": {"segments": 2}})
                store.save_to_disk(sess)
                seg_before = sess.game.state.world_clock["segment"]
                segs_before = get_time_config(sess.game.state)["segments"]

                store2 = diceflow.web.SessionStore()
                restored = store2.get(sess.session_id)
                self.assertIsNotNone(restored)
                # world_clock progress preserved
                self.assertEqual(restored.game.state.world_clock["segment"], seg_before)
                # custom world_model config preserved
                self.assertEqual(get_time_config(restored.game.state)["segments"], segs_before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class WorldModelSurfaceTest(unittest.TestCase):
    def test_turn_card_shows_time_advance(self) -> None:
        client = TestClient(app)
        sid = client.post("/api/sessions", json={"world_id": "border_town_tavern", "use_llm": False}).json()["session_id"]
        turn = client.post(f"/api/sessions/{sid}/turns", json={"input": "等待", "forced_roll": 15}).json()["turn"]
        self.assertTrue(
            any("时间推进到" in line for line in turn.get("mechanical_results", [])),
            f"expected a time-advance line, got {turn.get('mechanical_results')}",
        )

    def test_entity_record_exposes_relationship_history(self) -> None:
        client = TestClient(app)
        sid = client.post("/api/sessions", json={"world_id": "tomb_entrance", "use_llm": False}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "攻击守卫", "forced_roll": 15})
        status = client.get(f"/api/sessions/{sid}").json()["status"]
        guard = next(e for e in status["known_entities"] if e["id"] == "guard_1")
        self.assertIn("relationship_history", guard)
        self.assertEqual(len(guard["relationship_history"]), 1)


if __name__ == "__main__":
    unittest.main()
