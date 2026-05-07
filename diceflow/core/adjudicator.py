from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

from diceflow.core.adjudicator_heuristics import _heuristic_assessment, _success_changes
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
VALID_INTENT_KIND = {"deception", "stealth", "improvised", "use", "social", "discover", "create_environment", "transition"}

# Stable reason tags provided to the narrator for flavour and hooks.
# Computed from intent_kind + risk + method keywords.
VALID_REASON_TAGS = frozenset({
    "discover",
    "social",
    "stealth",
    "forceful",
    "world_transition_attempt",
    "needs_tool",
    "risky",
    "improvised",
})

# Keywords that force intent_kind to "discover", overriding LLM misclassification.
DISCOVER_KEYWORDS = frozenset({"有没有", "找找", "搜索", "搜查", "寻找", "翻找", "找找看", "看看有没有", "可疑", "线索", "脚印", "暗格"})


def _compute_reason_tags(assessment: dict[str, Any], action: Action) -> list[str]:
    """Derive stable reason_tags from the assessment's intent_kind and risk."""
    tags: list[str] = []
    intent_kind = str(assessment.get("intent_kind") or "")
    risk = str(assessment.get("risk") or "")

    if intent_kind == "discover":
        tags.append("discover")
    elif intent_kind in {"social", "deception"}:
        tags.append("social")
    elif intent_kind == "stealth":
        tags.append("stealth")
    elif intent_kind == "transition":
        tags.append("world_transition_attempt")
    elif intent_kind == "create_environment":
        tags.append("improvised")
    elif intent_kind == "improvised":
        tags.append("improvised")
    elif intent_kind == "use":
        tags.append("improvised")

    if risk == "high":
        tags.append("risky")

    method = str(action.get("method_text") or action.get("method") or "")
    if intent_kind != "discover" and any(term in method for term in DISCOVER_KEYWORDS):
        if "discover" not in tags:
            tags.append("discover")

    if "forceful" in str(action.get("approach_tags") or []):
        if "forceful" not in tags:
            tags.append("forceful")

    if not tags:
        tags.append("improvised")

    # Dedupe preserving order
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _apply_discover_override(action: Action, assessment: dict[str, Any]) -> None:
    """Force intent_kind=discover when method text contains discover keywords.
    This catches LLM misclassification (e.g. LLM returns improvised for search actions).
    Modifies the assessment dict in-place.
    """
    method = str(action.get("method_text") or action.get("method") or "").lower()
    if any(term in method for term in DISCOVER_KEYWORDS):
        assessment["intent_kind"] = "discover"
        # Discover is a peaceful search — never hostile-grade risk
        if assessment.get("risk") not in ("low", "medium"):
            assessment["risk"] = "low"
        # Override impossible difficulty — searching is never impossible
        if assessment.get("difficulty") == "impossible":
            assessment["difficulty"] = "medium"


class DynamicAdjudicator:
    """Fallback adjudication for plausible actions not covered by script rules."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def can_adjudicate(self, action: Action, validation: dict[str, Any], state: GameState) -> bool:
        if state.flags.get("game_over"):
            return False
        # Script-defined valid actions take priority — skip adjudication.
        if validation.get("valid") and action_family(action) != "unknown":
            return False
        return True

    def assess(self, action: Action, state: GameState, llm: Any | None = None) -> dict[str, Any]:
        if llm and hasattr(llm, "evaluate_dynamic_action"):
            for _ in range(2):
                try:
                    assessment = _sanitize_assessment(llm.evaluate_dynamic_action(action, state), action)
                    _apply_discover_override(action, assessment)
                    return assessment
                except Exception:
                    pass
        return _heuristic_assessment(action, state)

    def resolve(self, assessment: dict[str, Any]) -> CheckResult:
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

        # Discover / Transition failure — no HP cost, different narrative
        if intent_kind in {"discover", "transition"}:
            fail_changes: StateChanges = {"flags": {"dynamic_adjudication_used": True}}
            if result == "critical_fail":
                fail_changes["flags"]["heightened_alert"] = True
                fail_changes["events"] = ["你发出了声响，前路暂时不明。" if intent_kind == "transition" else "你弄出了声响，可能引起了注意。"]
            else:
                fail_changes["events"] = ["你没有找到明确的通路，需要再观察一下。" if intent_kind == "transition" else "你没有找到明确线索，但对周围环境有了更多了解。"]
            return fail_changes

        entity_changes: dict[str, dict[str, Any]] = {}
        if target_id and target_id in state.entities:
            entity_changes[target_id] = {"alert": True}
        elif not state.get_hostile_entities():
            return {
                "flags": {"dynamic_adjudication_used": True},
                "events": [f"{method}没有立刻奏效，你需要先找到更明确的路径或目标。"],
            }

        hp_loss = 2 if result == "critical_fail" or risk == "high" else 1
        return {
            "player": {"hp_delta": -hp_loss},
            "entities": entity_changes,
            "events": [f"{method}没有奏效，{target_name}识破了你的意图并逼近反制。"],
        }


def _sanitize_assessment(raw: object, action: Action | None = None) -> dict[str, Any]:
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

    result: dict[str, Any] = {
        "plausibility": plausibility,
        "difficulty": difficulty,
        "risk": risk,
        "intent_kind": intent_kind,
    }

    # Compute stable reason tags for narrator / hooks
    if action:
        result["reason_tags"] = _compute_reason_tags(result, action)
    else:
        result["reason_tags"] = _compute_reason_tags(result, {})

    # Never pass through spawn_entities — content generation is separate
    return result
