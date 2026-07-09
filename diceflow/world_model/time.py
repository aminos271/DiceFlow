from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.schemas import get_time_config

StateChanges = dict[str, Any]

# Action types / method keywords that can plausibly consume notable in-world
# time. Quick actions (inspect/attack/take/open) skip the LLM time judgment
# entirely — they are instant and would almost always return "none".
_TIME_PLAUSIBLE_TYPES = frozenset({"talk", "social", "use"})
_TIME_KEYWORDS = frozenset({
    "谈", "聊", "交谈", "商量", "讨论", "打听", "盘问",
    "搜", "寻找", "搜查", "翻找", "研究", "制作", "搬", "整理",
})


class TimePhase:
    """Action-driven world clock.

    Advances time on scripted triggers; when no trigger matches and an LLM
    is available, judges time impact qualitatively and maps the bucket to a
    segment advance. Emits a resolved ``set_clock`` plus a narration event.
    Time only advances when something triggers it (action-driven); ``invalid``
    turns never advance.
    """

    name = "time"
    order = 30

    def run(self, ctx: PhaseContext) -> StateChanges:
        if ctx.resolution_kind == "invalid":
            return {}

        cfg = get_time_config(ctx.state)
        trigger = _match_trigger(cfg.get("triggers", []), ctx)
        if trigger is None:
            return self._llm_path(ctx, cfg)

        advance = trigger.get("advance", {}) if isinstance(trigger.get("advance"), dict) else {}
        new_clock = _resolve_new_clock(ctx.state, cfg, advance)
        if new_clock is None:
            return {}
        return {"set_clock": new_clock, "events": [_event_for_segment(new_clock, cfg)]}

    def _llm_path(self, ctx: PhaseContext, cfg: dict) -> StateChanges:
        if not _is_time_plausible(ctx):
            return {}
        llm = ctx.llm
        if llm is None or not getattr(llm, "narration_available", False):
            return {}
        if not hasattr(llm, "judge_time_impact"):
            return {}
        try:
            verdict = llm.judge_time_impact(ctx.action, ctx.state)
        except Exception:
            return {}
        if not isinstance(verdict, dict):
            return {}
        impact = str(verdict.get("impact") or "none")
        magnitude_table = cfg.get("magnitude_table", {})
        n = magnitude_table.get(impact, 0) if isinstance(magnitude_table, dict) else 0
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            return {}
        new_clock = _resolve_new_clock(ctx.state, cfg, {"segments": n})
        if new_clock is None:
            return {}
        reason = str(verdict.get("reason") or "")
        event = _event_for_segment(new_clock, cfg)
        if reason:
            event = f"{event}（{reason}）"
        return {"set_clock": new_clock, "events": [event]}


def _is_time_plausible(ctx: PhaseContext) -> bool:
    """Whether an action could plausibly consume notable time (worth an LLM call)."""
    if str(ctx.action.get("type", "")) in _TIME_PLAUSIBLE_TYPES:
        return True
    method = " ".join(str(v) for v in (
        ctx.action.get("raw_input", ""), ctx.action.get("method_text", ""),
        ctx.action.get("method", ""),
    ) if v)
    return any(kw in method for kw in _TIME_KEYWORDS)


def _match_trigger(triggers: list, ctx: PhaseContext) -> dict | None:
    for trigger in triggers:
        if not isinstance(trigger, dict):
            continue
        when = trigger.get("when", {})
        if not isinstance(when, dict) or not when:
            continue
        if _matches_when(when, ctx):
            return trigger
    return None


def _matches_when(when: dict, ctx: PhaseContext) -> bool:
    action = ctx.action
    method_text = " ".join(str(v) for v in (
        action.get("raw_input", ""), action.get("method_text", ""),
        action.get("method", ""),
    ) if v)
    family = action_family(action)

    if "action_type" in when and str(action.get("type", "")) != str(when["action_type"]):
        return False
    if "action_family" in when and family != str(when["action_family"]):
        return False
    if "resolution_kind" in when and ctx.resolution_kind != str(when["resolution_kind"]):
        return False
    if "method_contains" in when and str(when["method_contains"]) not in method_text:
        return False
    return True


def _resolve_new_clock(state: Any, cfg: dict, advance: dict) -> dict[str, Any] | None:
    segments = cfg.get("segments") or ["morning"]
    if not isinstance(segments, list) or not segments:
        segments = ["morning"]
    cur = deepcopy(state.world_clock)
    cur.setdefault("day", 1)
    cur.setdefault("segment", segments[0])
    cur.setdefault("weather", "")

    if advance.get("next_day"):
        cur["day"] = int(cur["day"]) + 1
        cur["segment"] = segments[0]
        return cur

    try:
        n = int(advance.get("segments", 0))
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return None
    idx = segments.index(cur["segment"]) if cur["segment"] in segments else 0
    idx += n
    while idx >= len(segments):
        idx -= len(segments)
        cur["day"] = int(cur["day"]) + 1
    cur["segment"] = segments[idx]
    return cur


def _event_for_segment(clock: dict, cfg: dict) -> str:
    events = cfg.get("segment_events", {})
    segment = clock.get("segment", "")
    label = events.get(segment) if isinstance(events, dict) else None
    if label:
        return f"{label}（第{clock.get('day', 1)}天）。"
    return f"时间流逝，现在是{segment}（第{clock.get('day', 1)}天）。"
