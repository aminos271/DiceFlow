from __future__ import annotations

from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action
from diceflow.core.state import GameState


def _heuristic_assessment(action: Action, state: GameState) -> dict[str, str]:
    from diceflow.core.adjudicator import _sanitize_assessment

    method = " ".join(
        part for part in (
            str(action.get("raw_input") or "").strip(),
            str(action.get("method_text") or "").strip(),
            str(action.get("method") or "").strip(),
        )
        if part
    ).lower()
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

    # Open-ended social check BEFORE discover — inputs like "打听有没有活计"
    # should be social, not confused by "有没有" in DISCOVER_KEYWORDS.
    # Only strong social keywords here; "线索" is handled by discover below.
    if any(term in method for term in ["招募", "同伴", "队友", "结伴", "推荐", "打听", "消息", "活计", "活儿", "流言", "传闻", "同伙", "旅伴", "伙伴", "帮手", "同行", "一起去", "一起"]):
        return _sanitize_assessment(
            {
                "plausibility": "reasonable",
                "difficulty": "medium",
                "risk": "low",
                "intent_kind": "social",
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
        if target_id and target_id in entities:
            entities[target_id]["hostile"] = False
        flags["dynamic_distraction_created"] = True
        events = [f"对方的态度明显松动。"]
    elif intent_kind == "stealth":
        if target_id and target_id in entities:
            entities[target_id]["line_of_sight_blocked"] = True
        flags["dynamic_path_opened"] = True
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
        return {
            "entities": entities,
            "flags": flags,
            "events": [f"{method}制造出遮蔽，{target_name}一时难以判断你的位置。"],
        }

    if action_family(action) in {"throw", "use"} and intent_kind == "improvised":
        changes: dict[str, Any] = {
            "entities": entities,
            "flags": flags,
            "events": events,
        }
        if strong_success:
            changes["flags"]["dynamic_distraction_created"] = True
        return changes

    if strong_success:
        flags["dynamic_distraction_created"] = True
    return {"entities": entities, "flags": flags, "events": events}
