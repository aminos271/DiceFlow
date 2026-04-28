from __future__ import annotations

from typing import Any

from diceflow.core.intent import canonical_family, extract_approach_tags, normalize_action
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState
from diceflow.core.utils import result_label


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

    # Drop subsumed matches: a short alias contained inside a longer match
    # in the same text region belongs to the longer entity name.
    # e.g. "门" at pos 3 inside "木门" at pos 2 is discarded.
    mentions.sort(key=lambda m: (int(m["start"]), -int(m["length"])))
    filtered: list[dict[str, str | int]] = []
    for i, match in enumerate(mentions):
        start_i = int(match["start"])
        end_i = start_i + int(match["length"])
        subsumed = False
        for j, other in enumerate(mentions):
            if i == j:
                continue
            start_j = int(other["start"])
            end_j = start_j + int(other["length"])
            if start_j <= start_i and end_j >= end_i and int(other["length"]) > int(match["length"]):
                subsumed = True
                break
        if not subsumed:
            filtered.append(match)

    deduped: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for match in filtered:
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
    del action
    result = str(check.get("result"))
    event_text = "；".join(changes.get("events", []))
    if not event_text:
        event_text = "局势发生了变化，你必须立刻决定下一步。"

    ending = state.flags.get("ending")
    if ending:
        ending_text = state.script.get("ending_texts", {}).get(ending, f"结局：{ending}。")
        return f"{event_text} {ending_text}"

    return f"{result_label(result)}：{event_text} 当前生命 {state.player['hp']}/{state.player['max_hp']}。"


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
