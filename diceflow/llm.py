from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

import config
from diceflow.intent import canonical_family, extract_approach_tags, normalize_action
from diceflow.models import Action, CheckResult, StateChanges
from diceflow.state import GameState


PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class LLMClient:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_API_URL,
        )
        self.model = config.DEEPSEEK_MODEL_CHAT
        self.intent_prompt = (PROMPT_DIR / "intent_parser.txt").read_text(encoding="utf-8")
        self.narrator_prompt = (PROMPT_DIR / "narrator.txt").read_text(encoding="utf-8")

    def parse_intent(self, player_input: str, state: GameState) -> Action:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        content = self._chat(
            [
                {"role": "system", "content": self.intent_prompt},
                {
                    "role": "user",
                    "content": f"当前状态：{state_summary}\n玩家输入：{player_input}",
                },
            ],
            response_format={"type": "json_object"},
        )
        return _normalize_action(json.loads(content))

    def narrate(
        self,
        action: Action,
        check: CheckResult,
        changes: StateChanges,
        state: GameState,
    ) -> str:
        prompt = self.narrator_prompt.format(
            action=json.dumps(action, ensure_ascii=False),
            result=json.dumps(check, ensure_ascii=False),
            changes=json.dumps(changes, ensure_ascii=False),
            state=json.dumps(_compact_state(state), ensure_ascii=False),
        )
        return self._chat(
            [
                {"role": "system", "content": "你只输出叙事正文。"},
                {"role": "user", "content": prompt},
            ],
        ).strip()

    def _chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            **kwargs,
        )
        return response.choices[0].message.content or ""


def parse_intent(player_input: str, state: GameState, llm: LLMClient | None = None) -> Action:
    if llm:
        try:
            return llm.parse_intent(player_input, state)
        except Exception:
            pass
    return heuristic_parse_intent(player_input)


def narrate(
    action: Action,
    check: CheckResult,
    changes: StateChanges,
    state: GameState,
    llm: LLMClient | None = None,
) -> str:
    if llm:
        try:
            text = llm.narrate(action, check, changes, state)
            if text:
                return text
        except Exception:
            pass
    return fallback_narration(action, check, changes, state)


def heuristic_parse_intent(player_input: str) -> Action:
    text = player_input.strip()
    intent_family = "unknown"
    target = ""
    method = text
    tool = ""

    if any(word in text for word in ["火把"]):
        tool = "火把"
    elif any(word in text for word in ["铁钥匙", "钥匙"]):
        tool = "铁钥匙"
    elif any(word in text for word in ["短剑", "剑"]):
        tool = "短剑"

    if tool and any(word in text for word in ["用", "插", "拧", "烧", "点燃"]):
        intent_family = "use"
    elif any(word in text for word in ["开门", "开锁", "打开", "撬"]):
        intent_family = "open"
    elif any(word in text for word in ["推动", "推开", "拉开"]) and any(word in text for word in ["门", "箱"]):
        intent_family = "open"
    elif any(word in text for word in ["拨弄", "摆弄"]) and any(word in text for word in ["锁", "锁扣", "箱"]):
        intent_family = "open"
    elif any(word in text for word in ["攻击", "打", "砍", "刺", "挥剑"]):
        intent_family = "attack"
    elif any(word in text for word in ["烧", "火把", "点燃"]):
        intent_family = "use"
    elif any(word in text for word in ["拨弄", "摆弄", "推动", "拉动", "触碰", "按下"]):
        intent_family = "interact"
    elif any(word in text for word in ["检查", "观察", "搜索", "看", "调查"]):
        intent_family = "inspect"
    elif any(word in text for word in ["说", "问", "交涉", "威胁", "劝"]):
        intent_family = "talk"
    elif any(word in text for word in ["移动", "走", "靠近", "前往", "往", "接近", "潜行", "低调"]):
        intent_family = "move"
    elif any(word in text for word in ["逃", "后退", "闪避", "躲"]):
        intent_family = "flee"
    elif any(word in text for word in ["等待", "观望", "屏息"]):
        intent_family = "wait"

    if any(word in text for word in ["守卫", "卫兵", "敌人", "看守"]):
        target = "守卫"
    elif any(word in text for word in ["铁门"]):
        target = "铁门"
    elif any(word in text for word in ["木箱", "箱子"]):
        target = "木箱"
    elif any(word in text for word in ["骷髅"]):
        target = "骷髅"
    elif any(word in text for word in ["左门", "石门", "门", "出口", "锁"]):
        target = "左门"
    elif intent_family in {"open", "use"}:
        target = "左门"

    action = {
        "intent_family": intent_family,
        "type": intent_family,
        "target": target,
        "target_id": "",
        "tool": tool,
        "tool_id": tool,
        "approach_tags": extract_approach_tags(method),
        "method_text": method,
        "method": method,
    }
    return action


def fallback_narration(
    action: Action,
    check: CheckResult,
    changes: StateChanges,
    state: GameState,
) -> str:
    result = str(check.get("result"))
    event_text = "；".join(changes.get("events", []))
    if not event_text:
        event_text = "局势发生了变化，你必须立刻决定下一步。"

    ending = state.flags.get("ending")
    if ending == "victory":
        return f"{event_text} 守卫已经倒下，左门彻底敞开，你穿过冷光中的通道，逃出了古墓入口。"
    if ending == "death":
        return f"{event_text} 你的伤势压过了意志，视线沉入黑暗，本次冒险到此结束。"
    if ending == "timeout":
        return f"{event_text} 你拖得太久，古墓深处传来沉重机关声，退路被封死。"

    return f"{_result_label(result)}：{event_text} 当前生命 {state.player['hp']}/{state.player['max_hp']}。"


def _normalize_action(raw: dict[str, Any]) -> Action:
    family = canonical_family(raw.get("intent_family") or raw.get("type"))
    return normalize_action(
        {
            "intent_family": family,
            "type": family,
            "target": str(raw.get("target") or "").strip(),
            "target_id": str(raw.get("target_id") or "").strip(),
            "tool": str(raw.get("tool") or "").strip(),
            "tool_id": str(raw.get("tool_id") or "").strip(),
            "approach_tags": raw.get("approach_tags") or [],
            "method_text": str(raw.get("method_text") or raw.get("method") or "").strip(),
            "method": str(raw.get("method") or raw.get("method_text") or "").strip(),
        }
    )


def _compact_state(state: GameState) -> dict[str, Any]:
    snapshot = state.get_snapshot()
    return {
        "player": snapshot["player"],
        "scene": snapshot["scene"],
        "entities": {
            entity_id: {
                key: value
                for key, value in entity.items()
                if key not in {"aliases", "max_hp"}
            }
            for entity_id, entity in snapshot["entities"].items()
        },
        "flags": snapshot["flags"],
        "recent_events": snapshot["recent_events"],
    }


def _result_label(result: str) -> str:
    return {
        "critical_success": "大成功",
        "success": "成功",
        "fail": "失败",
        "critical_fail": "大失败",
    }.get(result, result)
