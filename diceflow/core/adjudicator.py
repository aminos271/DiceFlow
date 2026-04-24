from __future__ import annotations

import random
from copy import deepcopy
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
VALID_INTENT_KIND = {"deception", "stealth", "improvised", "use", "social", "discover", "create_environment"}

# Safe types for dynamically spawned entities (whitelist, not arbitrary types)
SAFE_SPAWN_TYPES = {"container", "item", "clue", "obstacle"}

# Allowed keys for dynamically spawned entity specs
SAFE_SPAWN_ALLOWED_KEYS = frozenset({"name", "aliases", "type", "tags", "contents", "metadata", "hooks", "lifecycle"})

# Minimal fallback for dynamic entity spawning when no script template exists.
FALLBACK_DYNAMIC_SPAWN: dict[str, Any] = {"name": "临时发现", "type": "clue", "tags": ["dynamic"]}

# Keywords that force intent_kind to "discover", overriding LLM misclassification.
DISCOVER_KEYWORDS = frozenset({"有没有", "找找", "搜索", "搜查", "寻找", "翻找", "找找看", "看看有没有", "可疑", "线索", "脚印", "暗格"})


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

    def assess(self, action: Action, state: GameState, llm: Any | None = None) -> dict[str, str]:
        if llm and hasattr(llm, "evaluate_dynamic_action"):
            for _ in range(2):
                try:
                    assessment = _sanitize_assessment(llm.evaluate_dynamic_action(action, state))
                    _apply_discover_override(action, assessment)
                    return assessment
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
            changes = _success_changes(action, state, target_id, target_name, method, intent_kind, result)
            spawn = assessment.get("spawn_entities", {})
            if isinstance(spawn, dict) and spawn:
                spawn_changes = changes.setdefault("spawn_entities", {})
                spawn_changes.update(deepcopy(spawn))
                changes["runtime_script_patch"] = _runtime_patch_for_spawn(spawn_changes, state)
            elif intent_kind in {"discover", "create_environment"}:
                spawn = _resolve_dynamic_spawn_from_script(intent_kind, state)
                if spawn:
                    changes["spawn_entities"] = spawn
                    changes["runtime_script_patch"] = _runtime_patch_for_spawn(spawn, state)
            return changes

        # Discover failure — no HP cost, different narrative
        if intent_kind == "discover":
            discover_fail: StateChanges = {"flags": {"dynamic_adjudication_used": True}}
            if result == "critical_fail":
                discover_fail["flags"]["heightened_alert"] = True
                discover_fail["events"] = ["你弄出了声响，可能引起了注意。"]
            else:
                discover_fail["events"] = ["你没有找到明确线索，但对周围环境有了更多了解。"]
            return discover_fail

        entity_changes: dict[str, dict[str, Any]] = {}
        if target_id and target_id in state.entities:
            entity_changes[target_id] = {"alert": True}

        hp_loss = 2 if result == "critical_fail" or risk == "high" else 1
        return {
            "player": {"hp_delta": -hp_loss},
            "entities": entity_changes,
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

    result: dict[str, Any] = {
        "plausibility": plausibility,
        "difficulty": difficulty,
        "risk": risk,
        "intent_kind": intent_kind,
    }

    # Pass through spawn_entities if safely defined
    if isinstance(data, dict):
        spawn = _sanitize_spawn_spec(data.get("spawn_entities"))
        if spawn:
            result["spawn_entities"] = spawn

    return result


def _sanitize_spawn_spec(spawn: object) -> dict[str, dict[str, Any]]:
    """Validate and sanitize a spawn_entities definition.

    Only allows container / item / clue / obstacle types and a whitelist
    of safe keys.  All spawned entities are marked ``category: persistent``
    so they survive beyond the current turn.
    """
    if not isinstance(spawn, dict):
        return {}

    safe_specs: dict[str, dict[str, Any]] = {}
    for entity_id, spec in spawn.items():
        if not isinstance(spec, dict):
            continue
        if str(spec.get("type", "")).lower() not in SAFE_SPAWN_TYPES:
            continue

        safe_spec: dict[str, Any] = {}
        for key in SAFE_SPAWN_ALLOWED_KEYS:
            if key in spec:
                safe_spec[key] = deepcopy(spec[key])

        if not safe_spec.get("name"):
            safe_spec["name"] = str(entity_id)

        # Persist — spawned entities survive across turns
        safe_spec.setdefault("lifecycle", {})
        if isinstance(safe_spec["lifecycle"], dict):
            safe_spec["lifecycle"]["category"] = "persistent"

        safe_specs[f"dynamic_{entity_id}"] = safe_spec

    return safe_specs


def _resolve_dynamic_spawn_from_script(intent_kind: str, state: GameState) -> dict[str, dict[str, Any]]:
    """Resolve spawn_entities from script-level dynamic_entity_templates, with fallback."""
    templates = state.script.get("dynamic_entity_templates", {})
    template = templates.get(intent_kind, FALLBACK_DYNAMIC_SPAWN)
    entity_id = f"dynamic_{intent_kind}_{state.turn_id}"
    return _sanitize_spawn_spec({entity_id: deepcopy(template)})


def _runtime_patch_for_spawn(spawn: dict[str, dict[str, Any]], state: GameState) -> dict[str, Any]:
    return {
        "id": f"dynamic_spawn_turn_{state.turn_id}",
        "source": "dynamic_adjudicator",
        "turn_id": state.turn_id,
        "ops": [
            {
                "op": "add_entity",
                "id": str(entity_id),
                "entity": deepcopy(entity),
            }
            for entity_id, entity in spawn.items()
        ],
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

    # discover — player searching / examining surroundings
    if any(term in method for term in DISCOVER_KEYWORDS) or ("检查" in method and "有没有" in method):
        return _sanitize_assessment(
            {
                "plausibility": "reasonable",
                "difficulty": "medium",
                "risk": "low",
                "intent_kind": "discover",
            }
        )

    # create_environment — player constructing / rearranging surroundings
    if any(term in method for term in ["设置", "制造", "布置", "堆", "堵", "挡住", "拦住"]):
        return _sanitize_assessment(
            {
                "plausibility": "reasonable",
                "difficulty": "medium",
                "risk": "medium",
                "intent_kind": "create_environment",
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
    entities: dict[str, dict[str, Any]] = {}
    if target_id and target_id in state.entities:
        entities[target_id] = {"distracted": True, "alert": False}
    events = [f"你的行动产生了效果。"]

    if intent_kind in {"deception", "social"}:
        entities[target_id]["hostile"] = False
        flags["dynamic_distraction_created"] = True
        events = [f"对方的态度明显松动。"]
    elif intent_kind == "stealth":
        flags["dynamic_path_opened"] = True
        entities[target_id]["line_of_sight_blocked"] = True
        events = [f"环境中出现了一个短暂的窗口。"]
    elif intent_kind == "discover":
        return {
            "flags": flags,
            "events": [f"你发现了一个新的可交互对象。"],
        }
    elif intent_kind == "create_environment":
        return {
            "flags": flags,
            "events": [f"你改变了当前环境。"],
        }
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
            changes["flags"]["dynamic_distraction_created"] = True
        return changes

    if strong_success:
        flags["dynamic_distraction_created"] = True
    return {"entities": entities, "flags": flags, "events": events}
