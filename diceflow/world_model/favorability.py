from __future__ import annotations

from typing import Any

from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.schemas import get_favorability_config

StateChanges = dict[str, Any]


class FavorabilityPhase:
    """Player<->NPC relationship.

    For NPCs whose favorability already changed via scripted outcomes this
    turn, record the delta to relationship history but do not re-emit a delta
    or run threshold reactions (the outcome table already set disposition).
    For other relation-relevant NPCs, judge the impact (LLM bucket, or
    heuristic fallback) and apply deterministic threshold reactions on
    crossing. ``invalid`` turns do nothing.
    """

    name = "favorability"
    order = 40

    def run(self, ctx: PhaseContext) -> StateChanges:
        if ctx.resolution_kind == "invalid":
            return {}
        cfg = get_favorability_config(ctx.state)
        npcs = _affected_npcs(ctx)
        if not npcs:
            return {}

        out: StateChanges = {}
        for npc_id in npcs:
            existing = _existing_favorability_delta(ctx, npc_id)
            if existing is not None:
                _record_history(out, npc_id, existing, _sentiment_for(existing), "脚本结果", ctx)
                continue
            if not _is_relation_relevant(ctx, npc_id):
                continue
            delta, sentiment, reason = self._judge(ctx, npc_id, cfg)
            if delta == 0:
                continue
            _emit_delta(out, npc_id, delta)
            _record_history(out, npc_id, delta, sentiment, reason, ctx)
            _apply_thresholds(out, ctx, npc_id, delta, cfg)
        return out

    def _judge(self, ctx: PhaseContext, npc_id: str, cfg: dict) -> tuple[int, str, str]:
        llm = ctx.llm
        if (llm is not None
                and getattr(llm, "narration_available", False)
                and hasattr(llm, "judge_favorability_effect")):
            try:
                verdict = llm.judge_favorability_effect(ctx.action, npc_id, ctx.turn_changes, ctx.state)
            except Exception:
                verdict = None
            if isinstance(verdict, dict):
                sentiment = str(verdict.get("sentiment") or "neutral")
                magnitude = str(verdict.get("magnitude") or "small")
                table = cfg.get("magnitude_table", {})
                base = table.get(magnitude, 0) if isinstance(table, dict) else 0
                try:
                    base = int(base)
                except (TypeError, ValueError):
                    base = 0
                if sentiment == "positive":
                    delta = base
                elif sentiment == "negative":
                    delta = -base
                else:
                    delta = 0
                return delta, sentiment, str(verdict.get("reason") or "")
        # heuristic fallback
        hp_delta = _hp_delta_for(ctx, npc_id)
        if hp_delta is not None and hp_delta < 0:
            return -2, "negative", "攻击/伤害"
        return 0, "neutral", ""


def _affected_npcs(ctx: PhaseContext) -> list[str]:
    state = ctx.state
    found: list[str] = []
    target_id = str(ctx.action.get("target_id") or "")
    if target_id and _is_npc(state.entities.get(target_id, {})) and target_id not in found:
        found.append(target_id)
    ent_changes = ctx.turn_changes.get("entities", {})
    if isinstance(ent_changes, dict):
        for eid, ch in ent_changes.items():
            if not isinstance(ch, dict):
                continue
            if "favorability_delta" in ch or "hp_delta" in ch:
                if _is_npc(state.entities.get(eid, {})) and eid not in found:
                    found.append(eid)
    return found


def _is_npc(entity: dict) -> bool:
    return entity.get("type") == "npc" or "npc" in entity.get("tags", [])


def _existing_favorability_delta(ctx: PhaseContext, npc_id: str) -> int | None:
    ent = ctx.turn_changes.get("entities", {}).get(npc_id)
    if not isinstance(ent, dict) or "favorability_delta" not in ent:
        return None
    try:
        return int(ent["favorability_delta"])
    except (TypeError, ValueError):
        return None


def _hp_delta_for(ctx: PhaseContext, npc_id: str) -> int | None:
    ent = ctx.turn_changes.get("entities", {}).get(npc_id)
    if not isinstance(ent, dict) or "hp_delta" not in ent:
        return None
    try:
        return int(ent["hp_delta"])
    except (TypeError, ValueError):
        return None


def _is_relation_relevant(ctx: PhaseContext, npc_id: str) -> bool:
    """An action targeting an NPC, or one that hurt an NPC, may move the
    relationship. The LLM/heuristic decides the magnitude (neutral -> 0)."""
    if _hp_delta_for(ctx, npc_id) is not None:
        return True
    target_id = str(ctx.action.get("target_id") or "")
    return target_id == npc_id


def _sentiment_for(delta: int) -> str:
    if delta > 0:
        return "positive"
    if delta < 0:
        return "negative"
    return "neutral"


def _record_history(out: StateChanges, npc_id: str, delta: int, sentiment: str, reason: str, ctx: PhaseContext) -> None:
    events = out.setdefault("relationship_events", {})
    events[npc_id] = {
        "delta": delta, "reason": reason or "", "sentiment": sentiment,
        "turn_id": ctx.state.turn_id,
    }


def _emit_delta(out: StateChanges, npc_id: str, delta: int) -> None:
    out.setdefault("entities", {}).setdefault(npc_id, {})["favorability_delta"] = delta


def _apply_thresholds(out: StateChanges, ctx: PhaseContext, npc_id: str, delta: int, cfg: dict) -> None:
    entity = ctx.state.entities.get(npc_id, {})
    old = int(entity.get("favorability", 0))
    new = old + delta
    current_hostile = bool(entity.get("hostile"))
    current_disposition = str(entity.get("disposition", "neutral"))
    mandated_hostile = current_hostile
    mandated_disposition = current_disposition
    for rule in cfg.get("thresholds", []):
        if not isinstance(rule, dict):
            continue
        crossed = False
        if "lte" in rule:
            try:
                x = int(rule["lte"])
            except (TypeError, ValueError):
                continue
            crossed = (old > x and new <= x)
        elif "gte" in rule:
            try:
                x = int(rule["gte"])
            except (TypeError, ValueError):
                continue
            crossed = (old < x and new >= x)
        if not crossed:
            continue
        setting = rule.get("set", {})
        if isinstance(setting, dict):
            if "hostile" in setting:
                mandated_hostile = bool(setting["hostile"])
            if "disposition" in setting:
                mandated_disposition = str(setting["disposition"])
    ent_change = out.setdefault("entities", {}).setdefault(npc_id, {})
    changed = False
    if mandated_hostile != current_hostile:
        ent_change["hostile"] = mandated_hostile
        changed = True
    if mandated_disposition != current_disposition:
        ent_change["disposition"] = mandated_disposition
        changed = True
    if changed:
        out.setdefault("add_npc_memory", {})[f"mem_rel_{npc_id}_{ctx.state.turn_id}"] = {
            "npc_entity_id": npc_id,
            "summary": f"关系变化：好感 {old} -> {new}（{mandated_disposition}）。",
            "sentiment": "negative" if (mandated_hostile or new < old) else "positive",
            "tags": ["favorability", "threshold"],
            "importance": 2,
        }
        out.setdefault("events", []).append(
            f"{entity.get('name', npc_id)}对你的态度变为{mandated_disposition}。"
        )
