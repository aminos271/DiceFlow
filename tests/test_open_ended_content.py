from __future__ import annotations

import unittest
from copy import deepcopy
from typing import Any

from diceflow.core.models import Action
from diceflow.core.open_ended_content import (
    _result_quality,
    open_ended_content_phase,
    validate_open_ended_patch,
)
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script

MOCK_ACTION: Action = {
    "intent_family": "social",
    "type": "social",
    "target": "酒馆",
    "target_id": "",
    "tool": "",
    "tool_id": "",
    "approach_tags": [],
    "method_text": "在酒馆里看看有没有人愿意结伴同行",
    "method": "在酒馆里看看有没有人愿意结伴同行",
}


class FakeOpenEndedContentLLM:
    def __init__(self, patch: dict[str, Any] | None = None) -> None:
        self.patch = deepcopy(patch) if patch else {}
        self.call_count = 0
        self.narration_available = True  # compat with narrate() duck-typing

    def generate_open_ended_content(
        self, action: Action, check: dict[str, Any], state: GameState, result_quality: str
    ) -> dict[str, Any]:
        self.call_count += 1
        self.last_action = action
        self.last_check = check
        self.last_quality = result_quality
        return deepcopy(self.patch)

    def generate_content_patch(self, context: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        self.last_action = context.get("action")
        self.last_check = context.get("check")
        self.last_quality = context.get("quality", "unknown")
        return deepcopy(self.patch)


class OpenEndedContentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script("border_town_tavern")
        self.state = GameState(self.script)

    # ── result_quality mapping ──────────────────────────────────────────

    def test_result_quality_mapping(self) -> None:
        self.assertEqual(_result_quality("critical_success"), "excellent")
        self.assertEqual(_result_quality("success"), "good")
        self.assertEqual(_result_quality("fail"), "bad")
        self.assertEqual(_result_quality("critical_fail"), "terrible")
        self.assertEqual(_result_quality("unknown"), "unknown")

    # ── Trigger conditions: positive cases ──────────────────────────────

    def test_social_success_triggers_open_ended_content(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "open_ended_1",
            "events": "一个旅人朝你点头，愿意结伴。",
            "ops": [
                {"op": "add_entity", "id": "dyn_companion", "entity": {
                    "name": "旅人", "type": "npc", "hp": 4, "max_hp": 4,
                    "tags": ["npc", "dynamic", "friendly"],
                    "metadata": {"allowed_actions": ["talk"], "actions": {
                        "talk": {"dc": 9, "outcomes": {"success": {"events": ["他愿意帮你。"]}}}
                    }}
                }},
                {"op": "set_flag", "key": "runtime.companion_found", "value": True},
            ],
        })
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }

        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)

        self.assertEqual(fake_llm.call_count, 1)
        self.assertIn(fake_llm.last_quality, {"excellent", "good", "bad", "terrible"})
        self.assertIsNotNone(changes.get("runtime_script_patch"))
        self.state.apply_changes(changes)
        self.assertIn("runtime.companion_found", self.state.flags)
        self.assertTrue(self.state.flags["runtime.companion_found"])

    def test_discover_critical_success_excellent_quality(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "open_ended_2",
            "events": "你在角落里发现了一张褪色的地图。",
            "ops": [
                {"op": "add_entity", "id": "dyn_faded_map", "entity": {
                    "name": "褪色地图", "type": "pickup", "tags": ["item", "dynamic"],
                    "metadata": {"allowed_actions": ["inspect"], "actions": {
                        "inspect": {"dc": 8, "outcomes": {"success": {"events": ["地图指向北方的废弃哨站。"]}}}
                    }}
                }},
                {"op": "set_flag", "key": "runtime.map_found", "value": True},
            ],
        })
        check = {
            "dc": 9, "roll": 20, "result": "critical_success", "dynamic": True,
            "assessment": {"intent_kind": "discover", "risk": "low", "difficulty": "easy", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)

        self.assertEqual(fake_llm.call_count, 1)
        self.assertEqual(fake_llm.last_quality, "excellent")
        self.assertIsNotNone(changes.get("runtime_script_patch"))
        self.state.apply_changes(changes)
        self.assertIn("dyn_faded_map", self.state.entities)

    def test_open_ended_discover_suppresses_generic_fallback_spawn(self) -> None:
        """When LLM produces richer output, no generic fallback spawn is created."""
        fake_llm = FakeOpenEndedContentLLM({
            "id": "open_ended_discover",
            "events": "你在酒馆里找到一个愿意交换消息的旅人。",
            "ops": [
                {"op": "set_flag", "key": "runtime.open_ended_discover_resolved", "value": True},
            ],
        })
        action: Action = {
            **deepcopy(MOCK_ACTION),
            "intent_family": "unknown",
            "type": "unknown",
            "target": "",
            "method_text": "搜索酒馆有没有合适队友",
            "method": "搜索酒馆有没有合适队友",
        }
        check = {
            "dc": 9, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "discover", "risk": "low", "difficulty": "easy", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(action, check, {}, self.state, fake_llm)

        self.assertEqual(fake_llm.call_count, 1)
        self.assertNotIn("spawn_entities", changes)
        self.assertIsNotNone(changes.get("runtime_script_patch"))
        self.state.apply_changes(changes)
        self.assertNotIn("临时发现", [e.get("name") for e in self.state.entities.values()])
        self.assertTrue(self.state.flags.get("runtime.open_ended_discover_resolved"))

    def test_improvised_fail_produces_trouble_flag_no_hp_loss(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "open_ended_3",
            "events": "你挪动杂物时发出声响，吧台旁的客人皱了皱眉头。",
            "ops": [
                {"op": "set_flag", "key": "runtime.unfriendly_atmosphere", "value": True},
            ],
        })
        check = {
            "dc": 13, "roll": 5, "result": "fail", "dynamic": True,
            "assessment": {"intent_kind": "improvised", "risk": "medium", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)

        self.assertEqual(fake_llm.call_count, 1)
        self.state.apply_changes(changes)
        self.assertTrue(self.state.flags.get("runtime.unfriendly_atmosphere"))

    def test_create_environment_good_quality_spawns_obstacle(self) -> None:
        action: Action = {**deepcopy(MOCK_ACTION), "intent_family": "create_environment",
                          "method_text": "在入口堆一些杂物做路障"}
        fake_llm = FakeOpenEndedContentLLM({
            "id": "open_ended_4",
            "events": "你用桌椅堆起了一个简易路障。",
            "ops": [
                {"op": "add_entity", "id": "dyn_barricade", "entity": {
                    "name": "简易路障", "type": "obstacle", "tags": ["obstacle", "dynamic"],
                    "metadata": {"allowed_actions": ["inspect"], "actions": {
                        "inspect": {"dc": 6, "outcomes": {"success": {"events": ["路障虽然简陋，但至少能拖延一阵。"]}}}
                    }}
                }},
            ],
        })
        check = {
            "dc": 13, "roll": 16, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "create_environment", "risk": "medium", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(action, check, {}, self.state, fake_llm)

        self.assertEqual(fake_llm.call_count, 1)
        self.state.apply_changes(changes)
        self.assertIn("dyn_barricade", self.state.entities)

    # ── Trigger conditions: skip cases ──────────────────────────────────

    def test_transition_intent_kind_skips_phase(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({"events": "should not be called"})
        check = {
            "dc": 9, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "transition", "risk": "low", "difficulty": "easy", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.assertEqual(fake_llm.call_count, 0)
        self.assertEqual(changes, {})

    def test_deception_intent_kind_skips_phase(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({"events": "nope"})
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "deception", "risk": "medium", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.assertEqual(fake_llm.call_count, 0)
        self.assertEqual(changes, {})

    def test_stealth_intent_kind_skips_phase(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({"events": "nope"})
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "stealth", "risk": "medium", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.assertEqual(fake_llm.call_count, 0)
        self.assertEqual(changes, {})

    def test_no_world_contract_skips_llm_phase(self) -> None:
        """Without a world contract, the LLM path is skipped.
        (no-LLM fallback may still trigger for discover.)"""
        fake_llm = FakeOpenEndedContentLLM({"events": "nope"})
        script = load_script("tomb_entrance")
        script.pop("world", None)  # remove world contract so LLM path is skipped
        state = GameState(script)
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, state, fake_llm)
        # social without world contract: LLM path skipped, no-LLM fallback doesn't apply
        self.assertEqual(fake_llm.call_count, 0)
        self.assertEqual(changes, {})

    def test_impossible_result_skips_phase(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({"events": "nope"})
        check = {
            "dc": 0, "roll": 0, "result": "impossible", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "high", "difficulty": "impossible", "plausibility": "impossible"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.assertEqual(fake_llm.call_count, 0)
        self.assertEqual(changes, {})

    def test_no_llm_but_discover_triggers_no_llm_fallback(self) -> None:
        """No LLM + discover success → no-LLM fallback creates entity via dynamic_entity_templates."""
        state = GameState(load_script("tomb_entrance"))
        check = {
            "dc": 9, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "discover", "risk": "low", "difficulty": "easy", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, state, None)
        self.assertIsNotNone(changes.get("runtime_script_patch"))
        state.apply_changes(changes)
        dyn_ids = [eid for eid in state.entities if eid.startswith("dynamic_")]
        self.assertEqual(len(dyn_ids), 1)

    def test_no_llm_non_discover_skips(self) -> None:
        """No LLM + non-discover → phase returns empty."""
        state = GameState(load_script("tomb_entrance"))
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, state, None)
        self.assertEqual(changes, {})

    # ── Validation: safety guardrails ───────────────────────────────────

    def test_invalid_entity_type_rejected(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "bad_patch",
            "events": "nope",
            "ops": [
                {"op": "add_entity", "id": "dyn_bad", "entity": {
                    "name": "攻城炮", "type": "weapon", "tags": ["weapon"],
                    "metadata": {"allowed_actions": [], "actions": {}}
                }},
            ],
        })
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.assertEqual(changes, {})

    def test_npc_safety_constraints_applied(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "bad_npc",
            "events": "一个看起来很危险的人靠近。",
            "ops": [
                {"op": "add_entity", "id": "dyn_hostile_npc", "entity": {
                    "name": "暴躁佣兵", "type": "npc", "hp": 99, "max_hp": 99,
                    "tags": ["npc", "hostile", "enemy"],
                    "metadata": {"allowed_actions": ["attack", "inspect"], "actions": {
                        "attack": {"dc": 12, "outcomes": {"success": {"player": {"hp_delta": -5}}}}
                    }}
                }},
            ],
        })
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.state.apply_changes(changes)
        dyn_ids = [eid for eid in self.state.entities if eid.startswith("dyn_")]
        if dyn_ids:
            npc = self.state.entities[dyn_ids[0]]
            self.assertLessEqual(npc["hp"], 5)
            self.assertLessEqual(npc["max_hp"], 5)
            self.assertNotIn("hostile", npc.get("tags", []))
            self.assertNotIn("enemy", npc.get("tags", []))

    def test_existing_entity_id_conflict_handled(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "conflict",
            "events": "nope",
            "ops": [
                {"op": "add_entity", "id": "barkeeper", "entity": {
                    "name": "假老板", "type": "npc", "hp": 3, "max_hp": 3,
                    "tags": ["npc"], "metadata": {"allowed_actions": ["talk"], "actions": {
                        "talk": {"dc": 8, "outcomes": {"success": {"events": ["你好。"]}}}
                    }}
                }},
            ],
        })
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        # barkeeper already exists → validation should discard
        self.state.apply_changes(changes)
        self.assertEqual(self.state.entities["barkeeper"]["name"], "酒馆老板")

    def test_critical_fail_produces_bad_quality(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "terrible",
            "events": "你打翻了酒杯，酒洒了一桌，老板投来不满的目光。",
            "ops": [
                {"op": "set_flag", "key": "runtime.barkeeper_annoyed", "value": True},
            ],
        })
        check = {
            "dc": 13, "roll": 1, "result": "critical_fail", "dynamic": True,
            "assessment": {"intent_kind": "improvised", "risk": "medium", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)

        self.assertEqual(fake_llm.call_count, 1)
        self.assertEqual(fake_llm.last_quality, "terrible")
        self.state.apply_changes(changes)
        self.assertTrue(self.state.flags.get("runtime.barkeeper_annoyed"))

    def test_events_extracted_from_patch(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "events_test",
            "events": "角落里的旅人抬头看了你一眼，又低头喝酒。",
            "ops": [
                {"op": "set_flag", "key": "runtime.glance_exchanged", "value": True},
            ],
        })
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "improvised", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.state.apply_changes(changes)
        self.assertIn("角落里的旅人抬头看了你一眼", str(self.state.recent_events))
        self.assertTrue(self.state.flags.get("runtime.glance_exchanged"))

    def test_events_only_patch_applied(self) -> None:
        fake_llm = FakeOpenEndedContentLLM({
            "id": "events_only",
            "events": "酒馆里的空气沉闷，没有人回应你的目光。",
            "ops": [],
        })
        check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "improvised", "risk": "low", "difficulty": "medium", "plausibility": "reasonable"},
        }
        changes = open_ended_content_phase(MOCK_ACTION, check, {}, self.state, fake_llm)
        self.state.apply_changes(changes)
        self.assertIn("酒馆里的空气沉闷", str(self.state.recent_events))


class ValidateOpenEndedPatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.script = load_script("border_town_tavern")
        self.state = GameState(self.script)

    def test_rejects_set_scene_op(self) -> None:
        raw = {
            "id": "bad",
            "ops": [{"op": "set_scene", "scene": {"name": "nowhere"}}],
        }
        patch, events = validate_open_ended_patch(raw, self.state)
        self.assertIsNone(patch)
        self.assertIsNone(events)

    def test_rejects_add_scene_action_op(self) -> None:
        raw = {
            "id": "bad",
            "ops": [{"op": "add_scene_action", "action": "move", "spec": {"dc": 5, "outcomes": {"success": {"events": ["ok"]}}}}],
        }
        patch, events = validate_open_ended_patch(raw, self.state)
        self.assertIsNone(patch)

    def test_rejects_flag_outside_namespace(self) -> None:
        raw = {
            "id": "bad",
            "ops": [{"op": "set_flag", "key": "bad_flag", "value": True}],
        }
        patch, events = validate_open_ended_patch(raw, self.state)
        self.assertIsNone(patch)

    def test_accepts_generated_flag(self) -> None:
        raw = {
            "id": "ok",
            "ops": [{"op": "set_flag", "key": "generated.test_flag", "value": True}],
        }
        patch, events = validate_open_ended_patch(raw, self.state)
        self.assertIsNotNone(patch)
        self.assertEqual(len(patch["ops"]), 1)

    def test_auto_prefix_dyn_on_entity_id(self) -> None:
        raw = {
            "id": "ok",
            "ops": [{"op": "add_entity", "id": "missing_prefix", "entity": {
                "name": "test", "type": "pickup", "tags": ["item"],
                "metadata": {"allowed_actions": [], "actions": {}}
            }}],
        }
        patch, events = validate_open_ended_patch(raw, self.state)
        self.assertIsNotNone(patch)
        self.assertEqual(patch["ops"][0]["id"], "dyn_missing_prefix")

    def test_rejects_entity_action_dc_above_world_limit(self) -> None:
        raw = {
            "id": "bad_dc",
            "ops": [{"op": "add_entity", "id": "dyn_bad_dc", "entity": {
                "name": "too hard", "type": "pickup", "tags": ["item"],
                "metadata": {"allowed_actions": ["inspect"], "actions": {
                    "inspect": {"dc": 99, "outcomes": {"success": {"events": ["nope"]}}}
                }}
            }}],
        }
        patch, events = validate_open_ended_patch(raw, self.state)
        self.assertIsNone(patch)
        self.assertIsNone(events)
