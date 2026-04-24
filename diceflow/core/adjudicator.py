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



