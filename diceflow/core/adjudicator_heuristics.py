from __future__ import annotations

from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action
from diceflow.core.state import GameState


def _heuristic_assessment(action: Action, state: GameState) -> dict[str, str]:
    from diceflow.core.adjudicator import _sanitize_assessment

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

    discover_keywords = frozenset({"有没有", "找找", "搜索", "搜查", "寻找", "翻找", "找找看", "看看有没有", "可疑", "线索", "脚印", "暗格"})
    if any(term in method for term in discover_keywords) or ("检查" in method and "有没有" in method):
        return _sanitize_assessment(
            {
                "plausibility": "reasonable",
                "difficulty": "easy",
                "risk": "low",
                "intent_kind": "discover",
            }
        )

    target_entity = state.entities.get(str(action.get("target_id") or ""), {})
    target_is_exit = target_entity.get("opened") or target_entity.get("type") == "door"
    method_has_transition = any(term in method for term in ["进入", "进去", "穿过", "走进", "前进", "探索"])
    if target_is_exit or (method_has_transition and (state.flags.get("door_open") or state.flags.get("scene_is_open"))):
        return _sanitize_assessment({
            "plausibility": "reasonable",
            "difficulty": "easy",
            "risk": "low",
            "intent_kind": "transition",
        })

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
) -> dict[str, Any]:
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
    elif intent_kind == "transition":
        return {
            "flags": {**flags, "scene_transition": True},
            "events": [f"你穿过{target_name}，进入了新的区域。"],
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
        changes: dict[str, Any] = {
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
