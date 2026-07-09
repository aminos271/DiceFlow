# 通用世界模型底座 — 时间子系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已落地的 `world_model` 底座上实现**时间子系统**（厚、动作驱动）：新增 `world_clock` 状态、`TimePhase` 注册阶段（order=30），按脚本触发表或 LLM 定性判断推进时间，并把时钟暴露给 narrator/adjudicator。

**Architecture:** `GameState` 新增 `world_clock` 槽 + `apply_changes` 认 `set_clock`/`advance_time` 两键；`schemas.py` 加时间默认配置；`world_model/time.py` 实现 `TimePhase`（先查脚本触发表，未命中且 LLM 可用时走 `judge_time_impact` 桶→`magnitude_table` 换算，无 LLM 则仅触发表）；`llm/client.py` 加 `judge_time_impact` + prompt；`Game.__init__` 注册 `TimePhase`；`build_turn_resolution`/`_compact_state` 暴露 `world_clock`。时间只在本回合有触发时推进（动作驱动），`invalid` 分支不推进。

**Tech Stack:** Python 3.12、pytest/unittest、现有 `diceflow.world_model` 包。

## Global Constraints

- 测试运行：`PYTHONPATH=. .venv/Scripts/python.exe -m pytest`（项目 venv 已就绪）。
- 测试风格：`unittest.TestCase`，`load_script("border_town_tavern")` / `load_script("tomb_entrance")` 构造 `GameState`，`Game(script=..., use_llm=False)`。
- 不破坏现有测试（合入 Plan 1 后 304 passed）。
- `PhaseContext`/`Phase`/`PhaseRegistry` 已在 Plan 1 落地：`from diceflow.world_model.base import Phase, PhaseContext`、`PhaseRegistry.register(phase)`。阶段 `order`：reaction=10、open_ended=20、**time=30**（本计划）、favorability=40（后续）。
- `get_world_model_config(state)` 已在 Plan 1 落地（`diceflow.world_model.schemas`），返回 `{**DEFAULT_WORLD_MODEL, **script["world_model"]}`。
- `resolution_kind` ∈ `{"standard","dynamic_adjudication","invalid","transition_attempt"}`。
- LLM 客户端 `LLMClient`：叙事/生成走 `narration_client` + `_narration_chat(..., response_format={"type":"json_object"})`，duck-typed `narration_available` 属性。`--no-llm` 时 `Game.llm is None`。
- 文件 UTF-8、LF。

## File Structure

- Modify: `diceflow/core/state.py` — `world_clock` 槽 + snapshot + `apply_changes` 两键 + `_advance_clock`。
- Modify: `diceflow/world_model/schemas.py` — `DEFAULT_WORLD_MODEL["time"]` 默认表 + `get_time_config(state)`。
- Create: `diceflow/world_model/time.py` — `TimePhase`（厚，动作驱动）。
- Modify: `diceflow/llm/client.py` — `judge_time_impact(action, state)` + prompt 加载。
- Create: `diceflow/content/prompts/time_judge.txt` — LLM 时间影响判断 prompt。
- Modify: `diceflow/app/game.py` — `Game.__init__` 注册 `TimePhase`；`build_turn_resolution` 暴露 `world_clock`。
- Modify: `diceflow/core/models.py` — `TurnResolution` 加 `world_clock` 字段。
- Modify: `diceflow/llm/client.py` `_compact_state` — 加 `world_clock`。
- Test: `tests/test_world_model_time.py` — state/schemas/phase/LLM/集成。

---

### Task 1: `GameState.world_clock` + `apply_changes` 两键 + snapshot

**Files:**
- Modify: `diceflow/core/state.py`（`__init__`、`get_snapshot`、`apply_changes`，新增 `_advance_clock`）
- Test: `tests/test_world_model_time.py`

**Interfaces:**
- Produces: `GameState.world_clock: dict`（`{day, segment, weather}`，默认 `{1,"morning",""}`）；`apply_changes` 认 `set_clock`（绝对，merge `day/segment/weather`）与 `advance_time`（相对 `{"segments": N}`，按 `script.world_model.time.segments` 滚动，缺省 5 段）；`get_snapshot` 含 `world_clock`。后续 `TimePhase` 依赖这些。

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_model_time.py`:

```python
from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


class WorldClockStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_default_clock(self) -> None:
        self.assertEqual(self.state.world_clock["day"], 1)
        self.assertEqual(self.state.world_clock["segment"], "morning")
        self.assertEqual(self.state.world_clock["weather"], "")

    def test_set_clock_applies(self) -> None:
        self.state.apply_changes({"set_clock": {"day": 2, "segment": "night", "weather": "雨"}})
        self.assertEqual(self.state.world_clock["day"], 2)
        self.assertEqual(self.state.world_clock["segment"], "night")
        self.assertEqual(self.state.world_clock["weather"], "雨")

    def test_set_clock_partial_merge(self) -> None:
        self.state.apply_changes({"set_clock": {"segment": "evening"}})
        self.assertEqual(self.state.world_clock["segment"], "evening")
        self.assertEqual(self.state.world_clock["day"], 1)  # unchanged

    def test_advance_time_rolls_within_day(self) -> None:
        self.state.apply_changes({"advance_time": {"segments": 2}})
        # morning -> noon -> evening
        self.assertEqual(self.state.world_clock["segment"], "evening")
        self.assertEqual(self.state.world_clock["day"], 1)

    def test_advance_time_rolls_over_to_next_day(self) -> None:
        # default 5 segments: morning,noon,evening,night,deep_night
        self.state.apply_changes({"advance_time": {"segments": 5}})
        self.assertEqual(self.state.world_clock["day"], 2)
        self.assertEqual(self.state.world_clock["segment"], "morning")

    def test_snapshot_contains_world_clock(self) -> None:
        snap = self.state.get_snapshot()
        self.assertIn("world_clock", snap)
        self.assertEqual(snap["world_clock"]["segment"], "morning")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py -q`
Expected: FAIL with `AttributeError: 'GameState' object has no attribute 'world_clock'`

- [ ] **Step 3: Write minimal implementation**

In `diceflow/core/state.py`，顶部加默认段常量（放在模块级，`_ensure_script_dict` 附近）：

```python
_DEFAULT_TIME_SEGMENTS = ["morning", "noon", "evening", "night", "deep_night"]
_DEFAULT_WORLD_CLOCK = {"day": 1, "segment": "morning", "weather": ""}
```

在 `GameState.__init__` 中，紧接 `self.npc_memories: dict[str, NpcMemory] = {}` 之后加：

```python
        self.world_clock: dict[str, Any] = deepcopy(
            self.script.get("world_clock", _DEFAULT_WORLD_CLOCK)
        )
        if "day" not in self.world_clock:
            self.world_clock.setdefault("day", 1)
            self.world_clock.setdefault("segment", "morning")
            self.world_clock.setdefault("weather", "")
```

在 `get_snapshot` 返回 dict 中加一项（紧接 `"npc_memories": ...` 之后）：

```python
            "world_clock": deepcopy(self.world_clock),
```

在 `apply_changes` 末尾、`self._refresh_end_state()` 之前，加两键处理：

```python
        set_clock = changes.get("set_clock")
        if isinstance(set_clock, dict):
            for key in ("day", "segment", "weather"):
                if key in set_clock:
                    self.world_clock[key] = set_clock[key]

        advance = changes.get("advance_time")
        if isinstance(advance, dict):
            try:
                segments_n = int(advance.get("segments", 0))
            except (TypeError, ValueError):
                segments_n = 0
            if segments_n > 0:
                self._advance_clock(segments_n)
```

新增方法（放在 `advance_turn` 附近）：

```python
    def _advance_clock(self, segments_n: int) -> None:
        segments = (
            self.script.get("world_model", {}).get("time", {}).get("segments")
            or _DEFAULT_TIME_SEGMENTS
        )
        if not isinstance(segments, list) or not segments:
            segments = _DEFAULT_TIME_SEGMENTS
        current = self.world_clock.get("segment", segments[0])
        idx = segments.index(current) if current in segments else 0
        idx += segments_n
        day = int(self.world_clock.get("day", 1))
        while idx >= len(segments):
            idx -= len(segments)
            day += 1
        self.world_clock["day"] = day
        self.world_clock["segment"] = segments[idx]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py -q`
Expected: PASS（6 项）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/core/state.py tests/test_world_model_time.py
git commit -m "feat(state): add world_clock slot with set_clock/advance_time"
```

---

### Task 2: `schemas.py` 时间默认配置 + `get_time_config`

**Files:**
- Modify: `diceflow/world_model/schemas.py`
- Test: `tests/test_world_model_time.py`

**Interfaces:**
- Produces: `DEFAULT_WORLD_MODEL["time"]`（含 `segments`/`magnitude_table`/`segment_events`/`triggers`）与 `get_time_config(state) -> dict`。`TimePhase`（Task 3）依赖 `get_time_config`。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_time.py`（`if __name__` 之前）:

```python
from diceflow.world_model.schemas import get_time_config


class TimeConfigTest(unittest.TestCase):
    def test_defaults_present(self) -> None:
        cfg = get_time_config(GameState(load_script("border_town_tavern")))
        self.assertIn("morning", cfg["segments"])
        self.assertEqual(cfg["magnitude_table"]["small"], 1)
        self.assertGreater(len(cfg["triggers"]), 0)

    def test_script_override(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        state.script["world_model"] = {"time": {"segments": ["dawn", "dusk"]}}
        cfg = get_time_config(state)
        self.assertEqual(cfg["segments"], ["dawn", "dusk"])
        # non-overridden keys still fall back to defaults
        self.assertIn("magnitude_table", cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py::TimeConfigTest -q`
Expected: FAIL with `ImportError: cannot import name 'get_time_config'`

- [ ] **Step 3: Write minimal implementation**

在 `diceflow/world_model/schemas.py` 把 `DEFAULT_WORLD_MODEL` 改为含 `time` 默认表，并加 `get_time_config`：

```python
DEFAULT_WORLD_MODEL: dict[str, Any] = {
    "time": {
        "segments": ["morning", "noon", "evening", "night", "deep_night"],
        "magnitude_table": {"none": 0, "small": 1, "medium": 2, "large": 4},
        "segment_events": {
            "morning": "天色渐明",
            "noon": "日上三竿",
            "evening": "暮色降临",
            "night": "夜幕笼罩",
            "deep_night": "夜深人静",
        },
        "triggers": [
            {"when": {"action_type": "wait"}, "advance": {"segments": 1}},
            {"when": {"resolution_kind": "transition_attempt"}, "advance": {"segments": 1}},
            {"when": {"method_contains": "过夜"}, "advance": {"next_day": True}},
            {"when": {"method_contains": "休息"}, "advance": {"next_day": True}},
            {"when": {"method_contains": "睡"}, "advance": {"next_day": True}},
        ],
    },
}


def get_world_model_config(state: Any) -> dict[str, Any]:
    script_cfg = state.script.get("world_model", {})
    if not isinstance(script_cfg, dict):
        script_cfg = {}
    return {**DEFAULT_WORLD_MODEL, **script_cfg}


def get_time_config(state: Any) -> dict[str, Any]:
    """Return the time subsystem config, with defaults for missing keys."""
    cfg = get_world_model_config(state).get("time", {})
    if not isinstance(cfg, dict):
        cfg = {}
    defaults = DEFAULT_WORLD_MODEL["time"]
    merged: dict[str, Any] = {}
    for key, default_val in defaults.items():
        if key in cfg:
            merged[key] = cfg[key]
        else:
            merged[key] = default_val
    return merged
```

在 `diceflow/world_model/__init__.py` 的导出里加 `get_time_config`（import 行与 `__all__` 都加）。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py -q`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/schemas.py diceflow/world_model/__init__.py tests/test_world_model_time.py
git commit -m "feat(world_model): add time config defaults and accessor"
```

---

### Task 3: `world_model/time.py` — `TimePhase`（触发表 + 滚动 + 事件，无 LLM 路径）

**Files:**
- Create: `diceflow/world_model/time.py`
- Modify: `diceflow/world_model/__init__.py`（导出 `TimePhase`）
- Test: `tests/test_world_model_time.py`

**Interfaces:**
- Consumes: `PhaseContext`/`Phase`（Plan 1）、`get_time_config`（Task 2）、`GameState.world_clock`/`apply_changes` 两键（Task 1）。
- Produces: `TimePhase`（`name="time"`, `order=30`）。`run(ctx)`：`invalid` 跳过；否则查 `triggers`（匹配 `action_type`/`action_family`/`resolution_kind`/`method_contains`），命中则按 `advance.segments` 或 `advance.next_day` 算出**已解析的新时钟**，返回 `{set_clock: new_clock, events: [event_text]}`；未命中返回 `{}`（LLM 路径在 Task 4 加）。`Game`（Task 5）依赖此类名与 order=30。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_time.py`:

```python
from diceflow.world_model.base import PhaseContext
from diceflow.world_model.time import TimePhase


def _ctx(state, *, action, resolution_kind, turn_changes=None) -> PhaseContext:
    return PhaseContext(
        action=action, validation={"valid": True}, check={"result": "success"},
        turn_changes=turn_changes or {}, state=state, llm=None,
        lorebook=None, resolution_kind=resolution_kind,
    )


class TimePhaseTriggerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_invalid_skips(self) -> None:
        ctx = _ctx(self.state, action={"type": "wait"}, resolution_kind="invalid")
        self.assertEqual(TimePhase().run(ctx), {})

    def test_wait_action_advances_one_segment(self) -> None:
        ctx = _ctx(self.state, action={"type": "wait", "method": "等待",
                                       "method_text": "等待"}, resolution_kind="standard")
        out = TimePhase().run(ctx)
        self.assertEqual(out["set_clock"]["segment"], "noon")
        self.assertIn("events", out)

    def test_transition_advances_one_segment(self) -> None:
        ctx = _ctx(self.state, action={"type": "move", "method_text": "进入通道"},
                   resolution_kind="transition_attempt")
        out = TimePhase().run(ctx)
        self.assertEqual(out["set_clock"]["segment"], "noon")

    def test_overnight_jumps_to_next_day_morning(self) -> None:
        self.state.apply_changes({"set_clock": {"day": 3, "segment": "night"}})
        ctx = _ctx(self.state, action={"type": "wait", "method_text": "在旅店过夜休息"},
                   resolution_kind="standard")
        out = TimePhase().run(ctx)
        self.assertEqual(out["set_clock"]["day"], 4)
        self.assertEqual(out["set_clock"]["segment"], "morning")

    def test_no_trigger_no_op(self) -> None:
        ctx = _ctx(self.state, action={"type": "attack", "method_text": "攻击守卫",
                                       "target_id": "guard_1"}, resolution_kind="standard")
        self.assertEqual(TimePhase().run(ctx), {})

    def test_segment_rollover_in_phase(self) -> None:
        self.state.apply_changes({"set_clock": {"segment": "deep_night"}})
        ctx = _ctx(self.state, action={"type": "wait", "method_text": "等待"},
                   resolution_kind="standard")
        out = TimePhase().run(ctx)
        # deep_night + 1 -> next day morning
        self.assertEqual(out["set_clock"]["day"], 2)
        self.assertEqual(out["set_clock"]["segment"], "morning")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py::TimePhaseTriggerTest -q`
Expected: FAIL with `ImportError: cannot import name 'TimePhase'`

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/world_model/time.py`:

```python
from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.schemas import get_time_config

StateChanges = dict[str, Any]


class TimePhase:
    """Action-driven world clock. Advances time on scripted triggers or
    (Task 4) LLM-judged impact. Emits resolved set_clock + a narration event.
    """

    name = "time"
    order = 30

    def run(self, ctx: PhaseContext) -> StateChanges:
        if ctx.resolution_kind == "invalid":
            return {}

        cfg = get_time_config(ctx.state)
        trigger = _match_trigger(cfg.get("triggers", []), ctx)
        if trigger is None:
            return {}  # LLM path added in Task 4

        advance = trigger.get("advance", {}) if isinstance(trigger.get("advance"), dict) else {}
        new_clock = _resolve_new_clock(ctx.state, cfg, advance)
        if new_clock is None:
            return {}
        event = _event_for_segment(new_clock, cfg)
        return {"set_clock": new_clock, "events": [event]}


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


def _resolve_new_clock(
    state: Any, cfg: dict, advance: dict
) -> dict[str, Any] | None:
    segments = cfg.get("segments") or ["morning"]
    cur = deepcopy(state.world_clock)
    cur.setdefault("day", 1)
    cur.setdefault("segment", segments[0])
    cur.setdefault("weather", "")

    if advance.get("next_day"):
        cur["day"] = int(cur["day"]) + 1
        cur["segment"] = segments[0]
        return cur

    n = advance.get("segments", 0)
    try:
        n = int(n)
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
```

Update `diceflow/world_model/__init__.py` 加 `TimePhase` 导入与 `__all__`。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py -q`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/time.py diceflow/world_model/__init__.py tests/test_world_model_time.py
git commit -m "feat(world_model): add TimePhase with action-driven triggers"
```

---

### Task 4: LLM `judge_time_impact` + `TimePhase` LLM 路径

**Files:**
- Modify: `diceflow/llm/client.py`（加 `judge_time_impact` + prompt 加载）
- Create: `diceflow/content/prompts/time_judge.txt`
- Modify: `diceflow/world_model/time.py`（LLM 路径）
- Test: `tests/test_world_model_time.py`

**Interfaces:**
- Produces: `LLMClient.judge_time_impact(action, state) -> dict`（`{impact: none|small|medium|large, reason}`，走 narration_client，JSON 桶）；`TimePhase` 在无触发命中且 `ctx.llm` 可用时调用之，按 `magnitude_table` 换算 segments，复用 `_resolve_new_clock`。`--no-llm` 时无触发即不推进。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_time.py`:

```python
class _FakeTimeLLM:
    narration_available = True

    def __init__(self, impact: str, reason: str = "闲谈良久") -> None:
        self.impact = impact
        self.reason = reason
        self.call_count = 0

    def judge_time_impact(self, action, state) -> dict:
        self.call_count += 1
        self.last_action = action
        return {"impact": self.impact, "reason": self.reason}


class TimePhaseLLMTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def _ctx(self, action, llm) -> PhaseContext:
        ctx = _ctx(self.state, action=action, resolution_kind="standard")
        ctx.llm = llm
        return ctx

    def test_llm_medium_bucket_advances_two_segments(self) -> None:
        # default magnitude_table: medium=2
        llm = _FakeTimeLLM("medium")
        out = TimePhase().run(self._ctx(
            {"type": "talk", "method_text": "和老板长谈一宿往事"}, llm))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(out["set_clock"]["segment"], "evening")  # morning+2

    def test_llm_none_bucket_no_op(self) -> None:
        llm = _FakeTimeLLM("none")
        out = TimePhase().run(self._ctx(
            {"type": "talk", "method_text": "随口问好"}, llm))
        self.assertEqual(llm.call_count, 1)
        self.assertEqual(out, {})

    def test_script_trigger_takes_priority_over_llm(self) -> None:
        llm = _FakeTimeLLM("large")
        # wait is a scripted trigger -> LLM not consulted
        out = TimePhase().run(self._ctx(
            {"type": "wait", "method_text": "等待"}, llm))
        self.assertEqual(llm.call_count, 0)
        self.assertEqual(out["set_clock"]["segment"], "noon")

    def test_no_llm_no_trigger_no_op(self) -> None:
        ctx = _ctx(self.state,
                   action={"type": "talk", "method_text": "随口问好"},
                   resolution_kind="standard")
        ctx.llm = None
        self.assertEqual(TimePhase().run(ctx), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py::TimePhaseLLMTest -q`
Expected: FAIL — 无 LLM 路径，`test_llm_medium_bucket_advances_two_segments` 返回 `{}`。

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/content/prompts/time_judge.txt`:

```text
你是一个 TRPG 时间判断助手。给定玩家本回合的行动与当前世界状态，判断这次行动在游戏世界里消耗了多少时间。

只输出 JSON：{"impact": "none|small|medium|large", "reason": "简短理由"}。
- none：几乎不耗时间（随口一句话、瞬间动作）。
- small：几分钟（简单交谈、翻看一件物品）。
- medium：约半小时到一小时（长谈、细致搜查、短途移动）。
- large：数小时（长眠之外的休整、长途、盛大活动）。
不要输出数值、不要改变世界状态、不要让玩家跳过核心挑战或直接通关。若行动本身不显著推进时间，给 none。
```

In `diceflow/llm/client.py` `LLMClient.__init__`，加载 prompt（紧接其它 `self.xxx_prompt = ...` 之后）：

```python
        self.time_judge_prompt = (PROMPT_DIR / "time_judge.txt").read_text(encoding="utf-8")
```

加方法（放在 `evaluate_dynamic_action` 之后）：

```python
    def judge_time_impact(self, action: Action, state: GameState) -> dict[str, Any]:
        content = self._narration_chat(
            [
                {"role": "system", "content": self.time_judge_prompt},
                {"role": "user", "content": json.dumps(
                    {
                        "action": action,
                        "current_clock": state.world_clock,
                        "scene": state.scene,
                        "recent_events": state.recent_events,
                    },
                    ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)
```

In `diceflow/world_model/time.py`，改 `TimePhase.run` 的未命中分支为走 LLM：

把 `if trigger is None: return {}` 改为：

```python
        if trigger is None:
            return self._llm_path(ctx, cfg)
```

并在 `TimePhase` 类内加方法：

```python
    def _llm_path(self, ctx: PhaseContext, cfg: dict) -> StateChanges:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py -q`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/content/prompts/time_judge.txt diceflow/llm/client.py diceflow/world_model/time.py tests/test_world_model_time.py
git commit -m "feat(world_model): LLM-judged time impact in TimePhase"
```

---

### Task 5: 注册 `TimePhase` + 暴露 `world_clock` 给 narrator

**Files:**
- Modify: `diceflow/core/models.py`（`TurnResolution` 加 `world_clock`）
- Modify: `diceflow/app/game.py`（`Game.__init__` 注册 `TimePhase`；`build_turn_resolution` 传 `world_clock`）
- Modify: `diceflow/llm/client.py`（`_compact_state` 加 `world_clock`）
- Test: `tests/test_world_model_time.py`

**Interfaces:**
- Produces：`Game.phases` 含 `TimePhase`；`TurnResolution.world_clock`；narrator/adjudicator 的 compact state 含 `world_clock`。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_time.py`:

```python
from diceflow.app.game import Game


class TimeIntegrationTest(unittest.TestCase):
    def test_wait_turn_advances_clock(self) -> None:
        game = Game(script=load_script("border_town_tavern"), use_llm=False)
        self.assertEqual(game.state.world_clock["segment"], "morning")
        record = game.run_turn("等待")
        self.assertEqual(game.state.world_clock["segment"], "noon")
        self.assertIn("world_clock", record.action or {})  # sanity: record exists
        # world_clock persisted in snapshot
        self.assertIn("world_clock", game.state.get_snapshot())

    def test_attack_does_not_advance_time(self) -> None:
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        before = dict(game.state.world_clock)
        game.run_turn("攻击守卫", forced_roll=15)
        self.assertEqual(game.state.world_clock, before)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py::TimeIntegrationTest -q`
Expected: FAIL — `test_wait_turn_advances_clock`：`world_clock` 仍是 morning（TimePhase 未注册）。

- [ ] **Step 3: Write minimal implementation**

In `diceflow/core/models.py`，`TurnResolution` 加字段（紧接 `lorebook_entries` 之后）：

```python
    world_clock: dict[str, Any]
```

In `diceflow/app/game.py` 顶部 import 加 `TimePhase`：

```python
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase
```
改为：
```python
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase
from diceflow.world_model.time import TimePhase
```

`Game.__init__` 中，紧接 `self.phases.register(OpenEndedPhase())` 之后加：

```python
        self.phases.register(TimePhase())
```

`build_turn_resolution` 返回的 `TurnResolution(...)` 调用里，加一个关键字参数（紧接 `**lorebook_context,` 之前）：

```python
        world_clock=deepcopy(state.world_clock),
```
（`deepcopy` 已在 game.py 顶部 import。）

In `diceflow/llm/client.py` `_compact_state` 返回 dict 中加（紧接 `"recent_history": ...` 之后）：

```python
        "world_clock": snapshot.get("world_clock", {}),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_time.py -q`
Expected: PASS。

Then full regression:

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS（304 + 新增，全绿）。若 `test_web_api` 或 `test_game_loop` 失败，检查 `build_turn_resolution` 的 `world_clock` 是否正确传入、`TurnResolution` 字段是否拼写一致。

- [ ] **Step 5: Commit**

```bash
git add diceflow/core/models.py diceflow/app/game.py diceflow/llm/client.py tests/test_world_model_time.py
git commit -m "feat(game): register TimePhase and expose world_clock to narrator"
```

---

## Self-Review（计划自审）

**1. Spec coverage**（对照设计文档 §5、§6.3、§6.4、§6.7 步骤 3-5）：
- §5.1 `world_clock` 数据模型 → Task 1 ✓
- §5.2 脚本触发表 + LLM 桶 + magnitude 换算 + 滚日 → Task 3（触发）+ Task 4（LLM）✓
- §5.3 配置点（segments/magnitude/triggers/segment_events）→ Task 2 ✓
- §5.4 `time_phase` order=30、动作驱动、invalid 跳过、transition 触发、event → Task 3 ✓
- §5.5 暴露进 `turn_resolution`/`_compact_state` → Task 5 ✓
- §6.3 `apply_changes` 新键 `advance_time`/`set_clock` → Task 1 ✓（`advance_time` 供将来 outcome 表相对推进；`TimePhase` 用解析后的 `set_clock`）
- §6.4 LLM `judge_time_impact` + prompt → Task 4 ✓
- §6.7 步骤 3（world_clock 槽）→ Task 1；步骤 4（time_phase LLM+回退）→ Task 3/4；步骤 5（LLM 方法+prompt）→ Task 4 ✓
- §6.7 步骤 6（Web 暴露）属 Plan 4，不在本计划。

**2. Placeholder scan**：无 TBD/TODO；所有代码步骤含完整代码。

**3. Type consistency**：
- `world_clock` 形状 `{day, segment, weather}` 在 Task 1/3/4/5 一致。
- `set_clock` / `advance_time` 两键在 Task 1 定义、Task 3/4 产出 `set_clock` 一致。
- `get_time_config(state)` 在 Task 2 定义、Task 3/4 使用一致。
- `TimePhase.name="time", order=30` 在 Task 3 定义、Task 5 注册时依赖。
- `judge_time_impact(action, state) -> {impact, reason}` 在 Task 4 定义并自洽。
- `_resolve_new_clock` / `_event_for_segment` 在 Task 3 定义、Task 4 LLM 路径复用，签名一致。

无类型/命名不一致。

## 后续（本计划之后）

- **Plan 3 — 好感子系统**：实体 `relationship` 子槽 + `apply_changes` 键 `relationship_events` + `schemas` 好感默认表 + `FavorabilityPhase`(order=40, LLM 桶+阈值反应+回退) + `judge_favorability_effect` + prompt。
- **Plan 4 — Web 暴露 + demo**：`StatusData.world_clock`/`relationship` + `border_town_tavern` 的 `world_model` 配置。
