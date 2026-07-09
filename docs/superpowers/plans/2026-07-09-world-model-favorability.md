# 通用世界模型底座 — 好感/关系子系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `world_model` 底座上实现**NPC 好感/关系子系统**（厚、action 无关、玩家↔NPC）：实体 `relationship` 历史 + `FavorabilityPhase`（order=40，LLM 定性桶→delta + 确定性阈值反应 + 启发式回退）+ `judge_favorability_effect` LLM 判断。

**Architecture:** `GameState.apply_changes` 认新键 `relationship_events`（追加实体 `relationship.history`）；`schemas.py` 加好感默认配置（`magnitude_table`/`thresholds`）；`world_model/favorability.py` 实现 `FavorabilityPhase`：扫描本回合受影响 NPC，对**已有脚本 favorability_delta** 的只记历史（不重复出 delta、不跑阈值，因为结果表已设 disposition），对**无脚本 delta** 的走 LLM 桶或启发式算 delta 并跑阈值反应（越线才翻转 disposition/hostile + 写 memory + event）。`llm/client.py` 加 `judge_favorability_effect` + prompt；`Game.__init__` 注册。

**Tech Stack:** Python 3.12、pytest/unittest、现有 `diceflow.world_model` 包。

## Global Constraints

- 测试：`PYTHONPATH=. .venv/Scripts/python.exe -m pytest`（合入 Plan 2 后 324 passed）。
- 测试风格：`unittest.TestCase`，`load_script("border_town_tavern")` / `load_script("tomb_entrance")`，`Game(use_llm=False)`。
- 阶段 `order`：reaction=10、open_ended=20、time=30、**favorability=40**（本计划）。
- `PhaseContext`/`PhaseRegistry`/`get_world_model_config` 已落地；`get_time_config` 模式可参照。
- `apply_changes` 已认 `entities`（含 `xxx_delta` 后缀由 `_apply_object_changes` 处理）、`add_npc_memory`、`events`。
- `resolution_kind` ∈ `{"standard","dynamic_adjudication","invalid","transition_attempt"}`。
- `action_family(action)` 来自 `diceflow.core.intent`。
- 实体 NPC 判定：`entity.get("type")=="npc" or "npc" in entity.get("tags",[])`。
- 文件 UTF-8、LF。

## File Structure

- Modify: `diceflow/core/state.py` — `apply_changes` 认 `relationship_events` 键（追加 `entity["relationship"]["history"]`）。
- Modify: `diceflow/world_model/schemas.py` — `DEFAULT_WORLD_MODEL["favorability"]` + `get_favorability_config`。
- Create: `diceflow/world_model/favorability.py` — `FavorabilityPhase`。
- Modify: `diceflow/llm/client.py` — `judge_favorability_effect` + prompt 加载。
- Create: `diceflow/content/prompts/favorability_judge.txt`。
- Modify: `diceflow/app/game.py` — `Game.__init__` 注册 `FavorabilityPhase`。
- Modify: `diceflow/world_model/__init__.py` — 导出 `FavorabilityPhase`/`get_favorability_config`。
- Test: `tests/test_world_model_favorability.py`。

---

### Task 1: `apply_changes` 认 `relationship_events` 键

**Files:**
- Modify: `diceflow/core/state.py`（`apply_changes`）
- Test: `tests/test_world_model_favorability.py`

**Interfaces:**
- Produces: `apply_changes` 认 `relationship_events: {npc_id: {delta, reason, sentiment, turn_id}}`，对每个 NPC 实体懒初始化 `entity["relationship"]={"history":[]}` 并追加（上限 20 条）。`FavorabilityPhase`（Task 3）产出此键。

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_model_favorability.py`:

```python
from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


class RelationshipEventsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_relationship_events_appends_history(self) -> None:
        self.state.apply_changes({"relationship_events": {
            "barkeeper": {"delta": 2, "reason": "攀谈甚欢", "sentiment": "positive", "turn_id": 1},
        }})
        rel = self.state.entities["barkeeper"]["relationship"]
        self.assertEqual(len(rel["history"]), 1)
        self.assertEqual(rel["history"][0]["delta"], 2)
        self.assertEqual(rel["history"][0]["sentiment"], "positive")

    def test_relationship_events_lazy_inits(self) -> None:
        self.assertNotIn("relationship", self.state.entities["barkeeper"])
        self.state.apply_changes({"relationship_events": {
            "barkeeper": {"delta": -1, "reason": "x", "sentiment": "negative", "turn_id": 2},
        }})
        self.assertIn("relationship", self.state.entities["barkeeper"])

    def test_relationship_events_unknown_entity_ignored(self) -> None:
        before = dict(self.state.entities)
        self.state.apply_changes({"relationship_events": {
            "no_such_npc": {"delta": 1, "reason": "x", "sentiment": "positive", "turn_id": 1},
        }})
        self.assertEqual(self.state.entities, before)

    def test_history_capped(self) -> None:
        for i in range(25):
            self.state.apply_changes({"relationship_events": {
                "barkeeper": {"delta": 1, "reason": "x", "sentiment": "positive", "turn_id": i},
            }})
        self.assertEqual(len(self.state.entities["barkeeper"]["relationship"]["history"]), 20)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py -q`
Expected: FAIL — `relationship` 不存在 / `KeyError`。

- [ ] **Step 3: Write minimal implementation**

在 `state.py` `apply_changes` 中，紧接 `advance_time` 处理块之后（`self.entity_journal.extend(...)` 之前）加：

```python
        relationship_events = changes.get("relationship_events")
        if isinstance(relationship_events, dict):
            for npc_id, ev in relationship_events.items():
                entity = self.entities.get(npc_id)
                if not isinstance(entity, dict) or not isinstance(ev, dict):
                    continue
                rel = entity.setdefault("relationship", {})
                if not isinstance(rel.get("history"), list):
                    rel["history"] = []
                rel["history"].append({
                    "turn_id": int(ev.get("turn_id", self.turn_id)),
                    "delta": int(ev.get("delta", 0)),
                    "reason": str(ev.get("reason", "")),
                    "sentiment": str(ev.get("sentiment", "neutral")),
                })
                rel["history"] = rel["history"][-20:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py -q`
Expected: PASS（4 项）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/core/state.py tests/test_world_model_favorability.py
git commit -m "feat(state): apply relationship_events to entity relationship history"
```

---

### Task 2: `schemas.py` 好感默认配置 + `get_favorability_config`

**Files:**
- Modify: `diceflow/world_model/schemas.py`
- Modify: `diceflow/world_model/__init__.py`
- Test: `tests/test_world_model_favorability.py`

**Interfaces:**
- Produces: `DEFAULT_WORLD_MODEL["favorability"]`（`magnitude_table`/`thresholds`）与 `get_favorability_config(state) -> dict`。`FavorabilityPhase`（Task 3）依赖。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_favorability.py`（`if __name__` 之前）:

```python
from diceflow.world_model.schemas import get_favorability_config


class FavorabilityConfigTest(unittest.TestCase):
    def test_defaults_present(self) -> None:
        cfg = get_favorability_config(GameState(load_script("border_town_tavern")))
        self.assertEqual(cfg["magnitude_table"]["medium"], 2)
        self.assertGreater(len(cfg["thresholds"]), 0)

    def test_override(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        state.script["world_model"] = {"favorability": {"magnitude_table": {"small": 2, "medium": 4, "large": 6}}}
        cfg = get_favorability_config(state)
        self.assertEqual(cfg["magnitude_table"]["medium"], 4)
        self.assertIn("thresholds", cfg)  # fallback for non-overridden keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py::FavorabilityConfigTest -q`
Expected: FAIL `ImportError: cannot import name 'get_favorability_config'`。

- [ ] **Step 3: Write minimal implementation**

在 `schemas.py` 的 `DEFAULT_WORLD_MODEL` 中加 `favorability` 键（紧接 `time` 之后）：

```python
    "favorability": {
        "magnitude_table": {"small": 1, "medium": 2, "large": 3},
        "thresholds": [
            {"lte": -5, "set": {"hostile": True, "disposition": "hostile"}},
            {"gte": 5, "set": {"disposition": "friendly"}},
        ],
    },
```

加访问器（紧接 `get_time_config` 之后）：

```python
def get_favorability_config(state: Any) -> dict[str, Any]:
    """Return the favorability subsystem config, with defaults for missing keys."""
    cfg = get_world_model_config(state).get("favorability", {})
    if not isinstance(cfg, dict):
        cfg = {}
    defaults = DEFAULT_WORLD_MODEL["favorability"]
    merged: dict[str, Any] = {}
    for key, default_val in defaults.items():
        merged[key] = cfg[key] if key in cfg else default_val
    return merged
```

`__init__.py` 导出加 `get_favorability_config`（import 行与 `__all__`）。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py -q`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/schemas.py diceflow/world_model/__init__.py tests/test_world_model_favorability.py
git commit -m "feat(world_model): add favorability config defaults and accessor"
```

---

### Task 3: `FavorabilityPhase`（启发式 + 阈值反应，无 LLM 路径）

**Files:**
- Create: `diceflow/world_model/favorability.py`
- Modify: `diceflow/world_model/__init__.py`
- Test: `tests/test_world_model_favorability.py`

**Interfaces:**
- Consumes: `PhaseContext`/`Phase`、`get_favorability_config`、`action_family`、`apply_changes` 的 `relationship_events`/`entities`/`add_npc_memory`。
- Produces: `FavorabilityPhase`（`name="favorability"`, `order=40`）。逻辑见下。`Game`（Task 5）注册它。

**相位逻辑（MVP）**：
1. `invalid` → `{}`。
2. 收集受影响 NPC：`action.target_id` 若为 NPC ∪ `turn_changes["entities"]` 中带 `hp_delta`/`favorability_delta` 的 NPC。
3. 对每个 NPC：
   - `existing_delta` = `turn_changes.entities[npc].favorability_delta`（脚本结果表已给）。若存在：记 `relationship_events`（sentiment 按符号、reason "脚本结果"），**不出 delta、不跑阈值**（结果表已设 disposition）。
   - 否则若该 NPC 本回合"关系相关"（`hp_delta<0` 或 `action_family ∈ {talk,social,attack,use,deception}` 且 target 是该 NPC）：
     - 无 LLM（本任务）：启发式 `hp_delta<0 → delta=-2,sentiment=negative`；否则 `delta=0`。
     - `delta!=0`：出 `entities[npc].favorability_delta=delta` + `relationship_events` + 阈值反应（`old=entity.favorability`, `new=old+delta`；阈值 `lte`/`gte` 越线 → 若与当前 disposition/hostile 不同则翻转 + `add_npc_memory` + event）。
   - LLM 路径 Task 4 加。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_favorability.py`:

```python
from diceflow.world_model.base import PhaseContext
from diceflow.world_model.favorability import FavorabilityPhase


def _ctx(state, *, action, resolution_kind="standard", turn_changes=None) -> PhaseContext:
    return PhaseContext(
        action=action, validation={"valid": True}, check={"result": "success"},
        turn_changes=turn_changes or {}, state=state, llm=None,
        lorebook=None, resolution_kind=resolution_kind,
    )


class FavorabilityPhaseHeuristicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_invalid_skips(self) -> None:
        ctx = _ctx(self.state, action={"type": "talk", "target_id": "barkeeper"},
                   resolution_kind="invalid")
        self.assertEqual(FavorabilityPhase().run(ctx), {})

    def test_existing_script_delta_recorded_no_extra_delta(self) -> None:
        # outcome table already gave +2 favorability and set disposition
        self.state.apply_changes({"entities": {"barkeeper": {"favorability_delta": 2}}})
        ctx = _ctx(self.state,
                   action={"type": "talk", "target_id": "barkeeper", "intent_family": "talk"},
                   turn_changes={"entities": {"barkeeper": {"favorability_delta": 2}}})
        out = FavorabilityPhase().run(ctx)
        self.assertNotIn("entities", out)  # no extra favorability_delta
        self.assertEqual(out["relationship_events"]["barkeeper"]["delta"], 2)

    def test_attack_lowers_favorability_via_heuristic(self) -> None:
        ctx = _ctx(self.state,
                   action={"type": "attack", "target_id": "barkeeper", "intent_family": "attack"},
                   turn_changes={"entities": {"barkeeper": {"hp_delta": -3}}})
        out = FavorabilityPhase().run(ctx)
        self.assertEqual(out["entities"]["barkeeper"]["favorability_delta"], -2)
        self.assertEqual(out["relationship_events"]["barkeeper"]["sentiment"], "negative")

    def test_threshold_cross_to_hostile(self) -> None:
        self.state.apply_changes({"set_entity_states": {"barkeeper": {"favorability": -4}}})
        ctx = _ctx(self.state,
                   action={"type": "attack", "target_id": "barkeeper", "intent_family": "attack"},
                   turn_changes={"entities": {"barkeeper": {"hp_delta": -3}}})
        out = FavorabilityPhase().run(ctx)
        # -4 + (-2) = -6 <= -5 -> hostile flip
        self.assertTrue(out["entities"]["barkeeper"].get("hostile"))
        self.assertEqual(out["entities"]["barkeeper"].get("disposition"), "hostile")
        self.assertIn("add_npc_memory", out)
        self.assertIn("events", out)

    def test_no_signal_no_change(self) -> None:
        ctx = _ctx(self.state,
                   action={"type": "inspect", "target_id": "barkeeper", "intent_family": "inspect"},
                   turn_changes={})
        self.assertEqual(FavorabilityPhase().run(ctx), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py::FavorabilityPhaseHeuristicTest -q`
Expected: FAIL `ImportError: cannot import name 'FavorabilityPhase'`。

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/world_model/favorability.py`:

```python
from __future__ import annotations

from typing import Any

from diceflow.core.intent import action_family
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.schemas import get_favorability_config

StateChanges = dict[str, Any]

_RELATION_RELEVANT_FAMILIES = frozenset({"talk", "social", "attack", "use", "deception"})


class FavorabilityPhase:
    """Player<->NPC relationship. LLM-judged delta for unscripted social
    actions, heuristic fallback, deterministic threshold reactions. Scripted
    favorability_delta is recorded to history but not re-emitted.
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
        # LLM path added in Task 4. Heuristic fallback:
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
    if not isinstance(ent, dict):
        return None
    if "favorability_delta" not in ent:
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
    if _hp_delta_for(ctx, npc_id) is not None:
        return True
    target_id = str(ctx.action.get("target_id") or "")
    return target_id == npc_id and action_family(ctx.action) in _RELATION_RELEVANT_FAMILIES


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
            "sentiment": "negative" if mandated_hostile or new < old else "positive",
            "tags": ["favorability", "threshold"],
            "importance": 2,
        }
        out.setdefault("events", []).append(
            f"{entity.get('name', npc_id)}对你的态度变为{mandated_disposition}。"
        )
```

`__init__.py` 导出加 `FavorabilityPhase`。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py -q`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/favorability.py diceflow/world_model/__init__.py tests/test_world_model_favorability.py
git commit -m "feat(world_model): add FavorabilityPhase with heuristic + threshold reactions"
```

---

### Task 4: LLM `judge_favorability_effect` + `FavorabilityPhase` LLM 路径

**Files:**
- Modify: `diceflow/llm/client.py`
- Create: `diceflow/content/prompts/favorability_judge.txt`
- Modify: `diceflow/world_model/favorability.py`
- Test: `tests/test_world_model_favorability.py`

**Interfaces:**
- Produces: `LLMClient.judge_favorability_effect(action, npc_id, turn_changes, state) -> {sentiment, magnitude, reason}`（走 narration_client，JSON 桶）；`FavorabilityPhase._judge` 在 `ctx.llm` 可用时调用之，按 `magnitude_table` + sentiment 换算 delta，无 LLM 时回退启发式。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_favorability.py`:

```python
class _FakeFavorabilityLLM:
    narration_available = True

    def __init__(self, sentiment, magnitude, reason="帮助搬货") -> None:
        self.sentiment = sentiment
        self.magnitude = magnitude
        self.reason = reason
        self.call_count = 0

    def judge_favorability_effect(self, action, npc_id, turn_changes, state) -> dict:
        self.call_count += 1
        self.last_npc = npc_id
        return {"sentiment": self.sentiment, "magnitude": self.magnitude, "reason": self.reason}


class FavorabilityPhaseLLMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def _ctx(self, action, llm, turn_changes=None) -> PhaseContext:
        ctx = _ctx(self.state, action=action, turn_changes=turn_changes)
        ctx.llm = llm
        return ctx

    def test_llm_positive_medium_advances_favorability(self) -> None:
        llm = _FakeFavorabilityLLM("positive", "medium")
        out = FavorabilityPhase().run(self._ctx(
            {"type": "social", "target_id": "barkeeper", "intent_family": "social",
             "method_text": "我帮老板搬货"}, llm))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(out["entities"]["barkeeper"]["favorability_delta"], 2)  # medium=2
        self.assertEqual(out["relationship_events"]["barkeeper"]["sentiment"], "positive")

    def test_llm_neutral_no_change(self) -> None:
        llm = _FakeFavorabilityLLM("neutral", "small")
        out = FavorabilityPhase().run(self._ctx(
            {"type": "talk", "target_id": "barkeeper", "intent_family": "talk",
             "method_text": "随口问好"}, llm))
        self.assertEqual(out, {})

    def test_existing_delta_skips_llm(self) -> None:
        llm = _FakeFavorabilityLLM("positive", "large")
        out = FavorabilityPhase().run(self._ctx(
            {"type": "talk", "target_id": "barkeeper", "intent_family": "talk"},
            llm, turn_changes={"entities": {"barkeeper": {"favorability_delta": 1}}}))
        self.assertEqual(llm.call_count, 0)
        self.assertNotIn("entities", out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py::FavorabilityPhaseLLMTest -q`
Expected: FAIL — 无 LLM 路径，`test_llm_positive_medium_advances_favorability` 返回 `{}`。

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/content/prompts/favorability_judge.txt`:

```text
你是 TRPG 关系判断助手。给定玩家本回合的行动、受影响的 NPC、本回合对该 NPC 已发生的变化与当前世界状态，判断这次行动对该 NPC 对玩家的关系影响。

只输出 JSON：{"sentiment": "positive|negative|neutral", "magnitude": "small|medium|large", "reason": "简短理由"}。
- positive：增进了好感（帮助、示好、送礼、解围）。
- negative：损害了好感（攻击、冒犯、欺骗被发现、威胁）。
- neutral：基本不影响关系（普通问候、观察、无关动作）。
- magnitude small/medium/large 表示影响程度。
不要输出数值、不要改变世界状态、不要让玩家无成本获得 NPC 绝对忠诚或秒杀关系。若行动不显著影响关系，给 neutral。
```

`llm/client.py` `__init__` 加载 prompt（紧接 `self.time_judge_prompt` 之后）：

```python
        self.favorability_judge_prompt = (PROMPT_DIR / "favorability_judge.txt").read_text(encoding="utf-8")
```

加方法（紧接 `judge_time_impact` 之后）：

```python
    def judge_favorability_effect(
        self, action: Action, npc_id: str, turn_changes: dict[str, Any], state: GameState
    ) -> dict[str, Any]:
        """Qualitatively judge how an action affects the relationship with one NPC."""
        npc = state.entities.get(npc_id, {})
        content = self._narration_chat(
            [
                {"role": "system", "content": self.favorability_judge_prompt},
                {"role": "user", "content": json.dumps(
                    {
                        "action": action,
                        "npc_id": npc_id,
                        "npc": {k: v for k, v in npc.items() if k in ("name", "disposition", "favorability", "personality")},
                        "turn_changes_for_npc": turn_changes.get("entities", {}).get(npc_id, {}),
                        "current_clock": state.world_clock,
                        "recent_events": state.recent_events,
                    },
                    ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)
```

`world_model/favorability.py` 改 `FavorabilityPhase._judge` 为先 LLM：

```python
    def _judge(self, ctx: PhaseContext, npc_id: str, cfg: dict) -> tuple[int, str, str]:
        llm = ctx.llm
        if llm is not None and getattr(llm, "narration_available", False) and hasattr(llm, "judge_favorability_effect"):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py -q`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/content/prompts/favorability_judge.txt diceflow/llm/client.py diceflow/world_model/favorability.py tests/test_world_model_favorability.py
git commit -m "feat(world_model): LLM-judged favorability effect in FavorabilityPhase"
```

---

### Task 5: 注册 `FavorabilityPhase` + 集成回归

**Files:**
- Modify: `diceflow/app/game.py`（`Game.__init__`）
- Test: `tests/test_world_model_favorability.py`

**Interfaces:**
- Produces：`Game.phases` 含 `FavorabilityPhase`（order=40，链末尾）。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_favorability.py`:

```python
from diceflow.app.game import Game


class FavorabilityIntegrationTest(unittest.TestCase):
    def test_attack_records_relationship_history(self) -> None:
        game = Game(script=load_script("border_town_tavern"), use_llm=False)
        game.run_turn("攻击酒馆老板", forced_roll=15)
        rel = game.state.entities["barkeeper"].get("relationship", {})
        self.assertTrue(rel.get("history"))  # heuristic -2 recorded

    def test_talk_records_history_without_double_delta(self) -> None:
        game = Game(script=load_script("border_town_tavern"), use_llm=False)
        fav_before = game.state.entities["barkeeper"].get("favorability", 0)
        game.run_turn("和老板攀谈", forced_roll=15)
        rel = game.state.entities["barkeeper"].get("relationship", {})
        self.assertTrue(rel.get("history"))
        # favorability changed by outcome only (no double application)
        fav_after = game.state.entities["barkeeper"].get("favorability", 0)
        self.assertNotEqual(fav_before, fav_after)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py::FavorabilityIntegrationTest -q`
Expected: FAIL — `FavorabilityPhase` 未注册，`relationship` 无 history。

- [ ] **Step 3: Write minimal implementation**

`game.py` 顶部 import 加：

```python
from diceflow.world_model.favorability import FavorabilityPhase
```

`Game.__init__` 中，紧接 `self.phases.register(TimePhase())` 之后加：

```python
        self.phases.register(FavorabilityPhase())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_favorability.py -q`
Expected: PASS。

Full regression:

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS（324 + 新增）。若 `test_dynamic_adjudicator` / `test_game_loop` 失败，检查阈值反应是否误翻了结果表已设的 disposition（Task 3 对 existing_delta 跳过阈值应避免此问题）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/app/game.py tests/test_world_model_favorability.py
git commit -m "feat(game): register FavorabilityPhase in default phase chain"
```

---

## Self-Review（计划自审）

**1. Spec coverage**（对照设计文档 §4、§6.3、§6.7 步骤 3-5 好感部分）：
- §4.1 数据模型 `relationship.history` → Task 1 ✓（`trust` 聚合标为可选，MVP 不做，YAGNI）
- §4.2 LLM 桶 + magnitude 换算 + 阈值反应 + 无 LLM 回退 → Task 3/4 ✓
- §4.3 配置点 `magnitude_table`/`thresholds` → Task 2 ✓
- §4.4 `favorability_phase` order=40、扫全量信号、invalid 跳过、action 无关 → Task 3 ✓
- §4.5 收敛现有（talk `favorability_delta` 不变，新阶段只在其上记历史+阈值）→ Task 3 `existing_delta` 路径 ✓
- §6.3 `apply_changes` 新键 `relationship_events` → Task 1 ✓
- §6.4 `judge_favorability_effect` + prompt → Task 4 ✓
- §6.7 步骤 4/5 → Task 3/4 ✓

**2. Placeholder scan**：无 TBD/TODO；所有代码步骤含完整代码。

**3. Type consistency**：
- `relationship_events` 形状 `{npc_id: {delta, reason, sentiment, turn_id}}` 在 Task 1/3 一致。
- `get_favorability_config(state)` 在 Task 2 定义、Task 3/4 使用一致。
- `FavorabilityPhase.name="favorability", order=40` 在 Task 3 定义、Task 5 注册依赖。
- `judge_favorability_effect(action, npc_id, turn_changes, state) -> {sentiment, magnitude, reason}` 在 Task 4 定义并自洽，fake LLM 签名一致。
- 阈值键 `lte`/`gte` + `set` 在 Task 2 默认表与 Task 3 `_apply_thresholds` 一致。

无类型/命名不一致。

## 后续（本计划之后）

- **Plan 4 — Web 暴露 + demo**：`StatusData.world_clock`/`relationship` + `border_town_tavern` 的 `world_model` 配置（time+favorability）。
