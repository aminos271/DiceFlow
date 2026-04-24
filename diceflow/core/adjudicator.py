from __future__ import annotations

import random
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState


DIFFICULTY_DC = {
    "easy": 9,
    "medium": 13,
    "hard": 17,
}

VALID_PLAUSIBILITY = {"reasonable", "unlikely", "impossible"}
VALID_DIFFICULTY = {"easy", "medium", "hard", "impossible"}
VALID_RISK = {"low", "medium", "high"}
VALID_INTENT_KIND = {"deception", "stealth", "improvised", "use", "social"}


class DynamicAdjudicator:
    """Fallback adjudication for plausible actions not covered by script rules."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def can_adjudicate(self, action: Action, validation: dict[str, Any], state: GameState) -> bool:
        if validation.get("valid") and action_family(action) != "unknown":
            return False
        if state.flags.get("game_over"):
            return False

        target_id = str(action.get("target_id") or "")
        if not target_id or target_id not in state.entities:
            return False

        target = state.entities[target_id]
        if not target.get("alive", True):
            return False

        # MVP boundary: only improvise around live guards/enemies for now.
        tags = set(target.get("tags", []))
        names = [str(target.get("name") or ""), *[str(alias) for alias in target.get("aliases", [])]]
        return "enemy" in tags or any("守卫" in name or "guard" in name.lower() for name in names)

    def assess(self, action: Action, state: GameState, llm: Any | None = None) -> dict[str, str]:
        if llm and hasattr(llm, "evaluate_dynamic_action"):
            for _ in range(2):
                try:
                    return _sanitize_assessment(llm.evaluate_dynamic_action(action, state))
                except Exception:
                    pass
        return _heuristic_assessment(action, state)

    def resolve(self, assessment: dict[str, str]) -> CheckResult:
        difficulty = assessment["difficulty"]
        if difficulty == "impossible":
            return {
                "dc": 0,
                "roll": 0,
                "result": "impossible",
                "dynamic": True,
                "assessment": assessment,
            }

        dc = DIFFICULTY_DC[difficulty]
        roll = self.rng.randint(1, 20)
        if roll == 1:
            result = "critical_fail"
        elif roll == 20:
            result = "critical_success"
        elif roll >= dc:
            result = "success"
        else:
            result = "fail"
        return {
            "dc": dc,
            "roll": roll,
            "result": result,
            "dynamic": True,
            "assessment": assessment,
        }

    def update_state(self, action: Action, check: CheckResult, state: GameState) -> StateChanges:
        assessment = check.get("assessment", {})
        if not isinstance(assessment, dict):
            assessment = {}

        result = str(check.get("result") or "")
        target_id = str(action.get("target_id") or "")
        target = state.entities.get(target_id, {})
        target_name = str(target.get("name") or action.get("target") or "目标")
        method = str(action.get("method_text") or action.get("method") or "这个办法")
        intent_kind = str(assessment.get("intent_kind") or "improvised")
        risk = str(assessment.get("risk") or "medium")

        if result == "impossible":
            return {
                "events": [f"{method}超出了当前世界与场景边界，不能直接成立。"],
            }

        if result in {"critical_success", "success"}:
            return _success_changes(action, state, target_id, target_name, method, intent_kind, result)

        hp_loss = 2 if result == "critical_fail" or risk == "high" else 1
        return {
            "player": {"hp_delta": -hp_loss},
            "entities": {target_id: {"alert": True}},
            "events": [f"{method}没有奏效，{target_name}识破了你的意图并逼近反制。"],
        }


def _sanitize_assessment(raw: object) -> dict[str, str]:
    data = raw if isinstance(raw, dict) else {}
    plausibility = str(data.get("plausibility") or "reasonable")
    difficulty = str(data.get("difficulty") or "medium")
    risk = str(data.get("risk") or "medium")
    intent_kind = str(data.get("intent_kind") or "improvised")

    if plausibility not in VALID_PLAUSIBILITY:
        plausibility = "reasonable"
    if difficulty not in VALID_DIFFICULTY:
        difficulty = "medium"
    if risk not in VALID_RISK:
        risk = "medium"
    if intent_kind not in VALID_INTENT_KIND:
        intent_kind = "improvised"
    if plausibility == "impossible":
        difficulty = "impossible"

    return {
        "plausibility": plausibility,
        "difficulty": difficulty,
        "risk": risk,
        "intent_kind": intent_kind,
    }


def _heuristic_assessment(action: Action, state: GameState) -> dict[str, str]:
    method = str(action.get("method_text") or action.get("method") or "").lower()
    family = action_family(action)
    target = state.entities.get(str(action.get("target_id") or ""), {})
    target_hostile = bool(target.get("hostile") or "hostile" in target.get("tags", []))

    impossible_terms = ["神器", "秒杀", "直接通关", "成为国王", "改写世界", "kill boss", "instant kill"]
    if any(term in method for term in impossible_terms):
        return _sanitize_assessment(
            {
                "plausibility": "impossible",
                "difficulty": "impossible",
                "risk": "high",
                "intent_kind": "improvised",
            }
        )

    if any(term in method for term in ["假装", "伪装", "巡逻", "投降", "骗", "冒充"]):
        intent_kind = "deception"
        difficulty = "medium" if target_hostile else "easy"
        risk = "medium"
    elif any(term in method for term in ["潜行", "绕", "悄悄", "躲", "藏"]):
        intent_kind = "stealth"
        difficulty = "medium"
        risk = "medium"
    elif any(term in method for term in ["贿赂", "金币", "钱", "交易"]):
        intent_kind = "social"
        difficulty = "hard" if target_hostile else "medium"
        risk = "low"
    elif any(term in method for term in ["烟", "火把", "油", "粉", "沙"]):
        intent_kind = "use"
        difficulty = "medium"
        risk = "high" if "火" in method or "油" in method else "medium"
    elif family == "throw" or any(term in method for term in ["石头", "噪音", "箱子", "堵门", "引开", "吸引"]):
        intent_kind = "improvised"
        difficulty = "easy" if any(term in method for term in ["石头", "噪音", "引开"]) else "medium"
        risk = "low"
    else:
        intent_kind = "improvised"
        difficulty = "medium"
        risk = "medium"

    return _sanitize_assessment(
        {
            "plausibility": "reasonable",
            "difficulty": difficulty,
            "risk": risk,
            "intent_kind": intent_kind,
        }
    )


def _success_changes(
    action: Action,
    state: GameState,
    target_id: str,
    target_name: str,
    method: str,
    intent_kind: str,
    result: str,
) -> StateChanges:
    strong_success = result == "critical_success"
    flags = {"dynamic_adjudication_used": True}
    entities: dict[str, dict[str, Any]] = {
        target_id: {
            "distracted": True,
            "alert": False,
        }
    }
    events = [f"{method}奏效了，{target_name}的注意力被短暂牵制。"]

    if intent_kind in {"deception", "social"}:
        entities[target_id]["hostile"] = False
        flags["guard_distracted"] = True
        events = [f"{target_name}暂时相信了你的说法，敌意明显松动。"]
    elif intent_kind == "stealth":
        flags["guard_bypassed"] = True
        entities[target_id]["line_of_sight_blocked"] = True
        events = [f"{target_name}看丢了你的动向，门前出现了短暂空档。"]
    elif intent_kind == "use":
        smoke_id = f"dynamic_smoke_{state.turn_id}"
        return {
            "entities": entities,
            "flags": flags,
            "spawn_entities": {
                smoke_id: {
                    "name": "临时烟雾",
                    "aliases": ["烟雾", "烟"],
                    "type": "temporary",
                    "tags": ["temporary", "obscuring"],
                    "available": True,
                    "visible": True,
                    "expires_after_turns": 2,
                }
            },
            "events": [f"{method}制造出遮蔽，{target_name}一时难以判断你的位置。"],
        }

    if action_family(action) in {"throw", "use"} and intent_kind == "improvised":
        noise_id = f"dynamic_noise_{state.turn_id}"
        changes: StateChanges = {
            "entities": entities,
            "flags": flags,
            "spawn_entities": {
                noise_id: {
                    "name": "临时噪音",
                    "aliases": ["噪音", "声响"],
                    "type": "temporary",
                    "tags": ["temporary", "noise", "distraction"],
                    "available": True,
                    "visible": True,
                    "expires_after_turns": 1,
                }
            },
            "events": events,
        }
        if strong_success:
            changes["flags"]["guard_distracted"] = True
        return changes

    if strong_success:
        flags["guard_distracted"] = True
    return {"entities": entities, "flags": flags, "events": events}
