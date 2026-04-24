from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from diceflow import config
from diceflow.core.intent import canonical_family, extract_approach_tags, normalize_action
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState


PROMPT_DIR = Path(__file__).resolve().parent.parent / "content" / "prompts"
LLM_RETRY_ATTEMPTS = 2
USE_VERBS = ["用", "插", "拧", "烧", "点燃"]
ACTION_KEYWORDS = {
    "open": ["open", "开门", "开锁", "打开", "撬"],
    "attack": ["attack", "攻击", "打", "砍", "刺", "挥剑", "砸"],
    "throw": ["throw", "投掷", "扔", "丢", "抛"],
    "take": ["take", "loot", "拿", "捡", "拾取", "取出", "翻找"],
    "interact": ["interact", "拨弄", "摆弄", "推动", "拉动", "触碰", "按下"],
    "inspect": ["inspect", "检查", "观察", "搜索", "看", "调查"],
    "talk": ["talk", "说", "问", "交涉", "威胁", "劝"],
    "move": ["move", "移动", "走", "靠近", "前往", "往", "接近", "潜行", "低调"],
    "flee": ["flee", "逃", "后退", "闪避", "躲"],
    "wait": ["wait", "等待", "观望", "屏息"],
}


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

    def evaluate_dynamic_action(self, action: Action, state: GameState) -> dict[str, Any]:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        action_summary = json.dumps(action, ensure_ascii=False)
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 TRPG 动态裁定助手，只做定性评估，不决定数值结果。"
                        "只输出 JSON：plausibility, difficulty, risk, intent_kind。"
                        "difficulty 只能是 easy、medium、hard、impossible。"
                        "禁止让玩家直接通关、秒杀 Boss、无成本获得神器、修改主线设定或跳过核心挑战。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"当前状态：{state_summary}\n玩家行动：{action_summary}",
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

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
        for _ in range(LLM_RETRY_ATTEMPTS):
            try:
                return llm.parse_intent(player_input, state)
            except Exception:
                pass
    return heuristic_parse_intent(player_input, state)


def narrate(
    action: Action,
    check: CheckResult,
    changes: StateChanges,
    state: GameState,
    llm: LLMClient | None = None,
) -> str:
    if llm:
        for _ in range(LLM_RETRY_ATTEMPTS):
            try:
                text = llm.narrate(action, check, changes, state)
                if text:
                    return text
            except Exception:
                pass
    return fallback_narration(action, check, changes, state)


def heuristic_parse_intent(player_input: str, state: GameState | None = None) -> Action:
    text = player_input.strip()
    method = text
    mentions = _entity_mentions(text, state)
    intent_family = _infer_family(text, mentions)
    target = ""
    target_id = ""
    tool = ""
    tool_id = ""

    if intent_family in {"use", "throw"} and len(mentions) >= 2:
        tool = mentions[0]["name"]
        tool_id = mentions[0]["id"]
        target = mentions[-1]["name"]
        target_id = mentions[-1]["id"]
    elif intent_family in {"use", "throw"} and mentions:
        if mentions[0].get("source") == "inventory":
            tool = mentions[0]["name"]
            tool_id = mentions[0]["id"]
        else:
            target = mentions[0]["name"]
            target_id = mentions[0]["id"]
    elif mentions:
        target = mentions[-1]["name"]
        target_id = mentions[-1]["id"]

    action = {
        "intent_family": intent_family,
        "type": intent_family,
        "target": target,
        "target_id": target_id,
        "tool": tool,
        "tool_id": tool_id,
        "approach_tags": extract_approach_tags(method),
        "method_text": method,
        "method": method,
    }
    return normalize_action(action, state)


def _infer_family(text: str, mentions: list[dict[str, str]]) -> str:
    has_use_verb = any(word in text for word in USE_VERBS)
    if has_use_verb and mentions:
        return "use"
    if any(word in text for word in ["推动", "推开", "拉开"]) and any(word in text for word in ["门", "箱", "盖"]):
        return "open"
    if any(word in text for word in ["拨弄", "摆弄"]) and any(word in text for word in ["锁", "锁扣", "箱"]):
        return "open"

    for family in ["take", "open", "throw", "attack", "inspect", "talk", "move", "flee", "wait", "interact"]:
        if any(keyword in text.lower() for keyword in ACTION_KEYWORDS[family]):
            return family
    return "unknown"


def _entity_mentions(text: str, state: GameState | None) -> list[dict[str, str]]:
    if not state:
        return []

    mentions: list[dict[str, str | int]] = []
    for item in state.player.get("inventory", []):
        _append_mention(mentions, text, str(item), str(item), str(item), source="inventory")

    for entity_id, entity in state.entities.items():
        if not state.is_interactable_entity(entity_id):
            continue
        names = [str(entity.get("name") or entity_id), *[str(alias) for alias in entity.get("aliases", [])]]
        for name in sorted(set(names), key=len, reverse=True):
            _append_mention(mentions, text, name, str(entity.get("name") or entity_id), entity_id)

    mentions.sort(key=lambda match: (int(match["start"]), -int(match["length"])))
    deduped: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for match in mentions:
        match_id = str(match["id"])
        if match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        deduped.append({"id": match_id, "name": str(match["name"]), "source": str(match["source"])})
    return deduped


def _append_mention(
    mentions: list[dict[str, str | int]],
    text: str,
    alias: str,
    display_name: str,
    entity_id: str,
    source: str = "entity",
) -> None:
    if not alias:
        return
    index = text.find(alias)
    if index >= 0:
        mentions.append(
            {
                "start": index,
                "length": len(alias),
                "name": display_name,
                "id": entity_id,
                "source": source,
            }
        )


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
    if ending:
        ending_text = state.script.get("ending_texts", {}).get(ending, f"结局：{ending}。")
        return f"{event_text} {ending_text}"

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
