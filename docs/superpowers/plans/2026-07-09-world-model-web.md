# 通用世界模型底座 — Web 暴露 + demo 配置 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让世界模型对前端可见、可配置：`StatusData` 暴露 `world_clock` 与 NPC 关系历史计数；`validate_script` 放行 `world_model`/`world_clock` 顶层键；`WorldBootstrap` 透传这两键；给 `border_town_tavern` 加一份 demo `world_model` 配置演示"随用随改"；前端状态栏显示当前时段/天数。

**Architecture:** 纯增量。后端 `web/server.py` 的 `StatusData`+`_build_status`+`_entity_record` 加字段；`validation.py` 加两个可选顶层键；`bootstrap.py` 的 `WorldBootstrap` 加两字段并透传；两个 border_town_tavern 内容文件加 demo 配置；前端 `StatusSidebar.jsx` 状态区显示 `world_clock`。

**Tech Stack:** Python 3.12、pytest、FastAPI TestClient、React。

## Global Constraints

- 测试：`PYTHONPATH=. .venv/Scripts/python.exe -m pytest`（合入 Plan 3 后 340 passed）。
- 前端无 pytest 覆盖；前端步骤为手动验证（`npm --prefix web run build` 通过即可）。
- `get_time_config`/`get_favorability_config` 已落地（`diceflow.world_model.schemas`）。
- `GameState.world_clock`、`entity["relationship"]["history"]` 已落地。
- `load_script(name)` 读 `content/scripts/<name>.yaml`，`validate_script` 拒绝未知顶层键。
- Web 会话经 `WorldBootstrap`（`bootstrap_from_lorebook`/`_bootstrap_from_world_config`）→ `to_script_dict`。
- 文件 UTF-8、LF。

## File Structure

- Modify: `diceflow/scripting/validation.py` — 加 `world_model`/`world_clock` 可选顶层键。
- Modify: `diceflow/core/bootstrap.py` — `WorldBootstrap` 加两字段 + `to_script_dict` 透传 + `_bootstrap_from_world_config` 读取。
- Modify: `diceflow/content/scripts/border_town_tavern.yaml` — 加 demo `world_model` + `world_clock`。
- Modify: `diceflow/content/worlds/border_town_tavern/bootstrap.yaml` — 同步加 demo 配置。
- Modify: `diceflow/web/server.py` — `StatusData.world_clock` + `_build_status` + `_entity_record` 关系历史。
- Modify: `web/src/components/StatusSidebar.jsx` — 显示时段/天数。
- Test: `tests/test_world_model_web.py`。

---

### Task 1: `validate_script` 放行 `world_model`/`world_clock`

**Files:**
- Modify: `diceflow/scripting/validation.py`
- Test: `tests/test_world_model_web.py`

**Interfaces:**
- Produces：`world_model`（dict）与 `world_clock`（dict）成为合法可选顶层键，`load_script` 不再因它们报错。后续 Task 3 的 demo YAML 依赖。

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_model_web.py`:

```python
from __future__ import annotations

import copy
import unittest

from diceflow.scripting.loader import load_script


class ScriptWorldModelKeysTest(unittest.TestCase):
    def test_border_town_tavern_loads_with_world_model(self) -> None:
        s = load_script("border_town_tavern")
        self.assertIn("world_model", s)
        self.assertIn("world_clock", s)

    def test_validate_accepts_world_model_and_world_clock(self) -> None:
        s = load_script("border_town_tavern")
        # adding extra world_model subkeys still validates
        s["world_model"]["time"]["segments"] = ["dawn", "noon", "dusk"]
        from diceflow.scripting.validation import validate_script
        validate_script(s)  # should not raise


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py -q`
Expected: FAIL — `world_model` not in script (demo YAML 未加) 或 validation 拒绝。

- [ ] **Step 3: Write minimal implementation**

`validation.py` 的 `OPTIONAL_TOP_LEVEL_TYPES` 加两项（紧接 `"dynamic_entity_templates": dict,` 之后）：

```python
    "world_model": dict,
    "world_clock": dict,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py -q`
Expected: 仍 FAIL（demo YAML 未加，Task 3 加）。本任务只改 validation；先跑全量确认 validation 改动不破坏现有：

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS（340，validation 放行不影响现有脚本）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/scripting/validation.py tests/test_world_model_web.py
git commit -m "feat(scripting): allow world_model/world_clock top-level keys"
```

---

### Task 2: `WorldBootstrap` 透传 `world_model`/`world_clock`

**Files:**
- Modify: `diceflow/core/bootstrap.py`
- Test: `tests/test_world_model_web.py`

**Interfaces:**
- Produces：`WorldBootstrap.world_model`、`WorldBootstrap.world_clock` 字段；`to_script_dict()` 含二者；`_bootstrap_from_world_config` 读取 `config.get("world_model")`/`config.get("world_clock")`。Web 创建的世界可自定义世界模型。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_web.py`:

```python
from diceflow.core.bootstrap import WorldBootstrap


class WorldBootstrapPassThroughTest(unittest.TestCase):
    def test_to_script_dict_carries_world_model_and_clock(self) -> None:
        wb = WorldBootstrap(
            world_id="t", title="t",
            world_model={"time": {"segments": ["dawn", "dusk"]}},
            world_clock={"day": 2, "segment": "dusk", "weather": ""},
        )
        s = wb.to_script_dict()
        self.assertEqual(s["world_model"]["time"]["segments"], ["dawn", "dusk"])
        self.assertEqual(s["world_clock"]["day"], 2)

    def test_defaults_empty(self) -> None:
        s = WorldBootstrap(world_id="t", title="t").to_script_dict()
        self.assertEqual(s.get("world_model"), {})
        self.assertEqual(s.get("world_clock"), {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py::WorldBootstrapPassThroughTest -q`
Expected: FAIL — `WorldBootstrap.__init__() got an unexpected keyword argument 'world_model'`。

- [ ] **Step 3: Write minimal implementation**

`bootstrap.py` `WorldBootstrap` dataclass 加两字段（紧接 `locations: dict = field(default_factory=dict)` 之后）：

```python
    world_model: dict = field(default_factory=dict)
    world_clock: dict = field(default_factory=dict)
```

`to_script_dict` 返回 dict 末尾加（紧接 `"locations": deepcopy(self.locations),` 之后）：

```python
            "world_model": deepcopy(self.world_model),
            "world_clock": deepcopy(self.world_clock),
```

`_bootstrap_from_world_config` 的 `WorldBootstrap(...)` 构造加两参（紧接 `locations=deepcopy(config.get("locations", {})),` 之后）：

```python
        world_model=deepcopy(config.get("world_model", {})),
        world_clock=deepcopy(config.get("world_clock", {})),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py -q`
Expected: PASS（含 Task 1 的，除 demo YAML 那条仍 fail 直到 Task 3）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/core/bootstrap.py tests/test_world_model_web.py
git commit -m "feat(bootstrap): pass world_model/world_clock through WorldBootstrap"
```

---

### Task 3: border_town_tavern demo `world_model` 配置

**Files:**
- Modify: `diceflow/content/scripts/border_town_tavern.yaml`
- Modify: `diceflow/content/worlds/border_town_tavern/bootstrap.yaml`
- Test: `tests/test_world_model_web.py`

**Interfaces:**
- Produces：border_town_tavern 剧本与世界引导都带一份 demo `world_model`（自定义时段/magnitude/阈值）与起始 `world_clock`，演示"随用随改"。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_web.py`:

```python
from diceflow.world_model.schemas import get_favorability_config, get_time_config
from diceflow.core.state import GameState


class BorderTownDemoConfigTest(unittest.TestCase):
    def test_script_exposes_custom_time_config(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        cfg = get_time_config(state)
        # demo overrides segments to a 4-slice day
        self.assertEqual(cfg["segments"], ["清晨", "正午", "黄昏", "深夜"])
        self.assertEqual(cfg["world_clock_start"]["segment"], "清晨")  # via world_clock

    def test_script_exposes_custom_favorability_thresholds(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        cfg = get_favorability_config(state)
        # demo raises the hostile threshold to -4
        lte = [r for r in cfg["thresholds"] if "lte" in r]
        self.assertEqual(lte[0]["lte"], -4)

    def test_state_starts_at_demo_clock(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        self.assertEqual(state.world_clock["segment"], "清晨")
        self.assertEqual(state.world_clock["day"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py::BorderTownDemoConfigTest -q`
Expected: FAIL — segments 仍是默认 `["morning",...]`。

- [ ] **Step 3: Write minimal implementation**

在 `content/scripts/border_town_tavern.yaml` 的 `world:` 段之后（`entities:` 之前）加：

```yaml
world_clock:
  day: 1
  segment: 清晨
  weather: ''
world_model:
  time:
    segments: [清晨, 正午, 黄昏, 深夜]
    magnitude_table: {none: 0, small: 1, medium: 2, large: 4}
    segment_events:
      清晨: 晨光熹微
      正午: 日头高悬
      黄昏: 暮色四合
      深夜: 夜阑人静
    triggers:
      - {when: {method_contains: 过夜}, advance: {next_day: true}}
      - {when: {method_contains: 休息}, advance: {next_day: true}}
      - {when: {action_type: wait}, advance: {segments: 1}}
      - {when: {resolution_kind: transition_attempt}, advance: {segments: 1}}
  favorability:
    magnitude_table: {small: 1, medium: 2, large: 3}
    thresholds:
      - {lte: -4, set: {hostile: true, disposition: hostile}}
      - {gte: 6, set: {disposition: friendly}}
```

在 `content/worlds/border_town_tavern/bootstrap.yaml` 的 `world:` 段之后加同样的 `world_clock` 与 `world_model` 块（YAML 内容同上）。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py -q`
Expected: PASS（全部）。

Full regression（确认 demo 配置不破坏 border_town_tavern 相关测试，注意时段名改变可能影响 time 测试——本计划 time 测试用默认段，不依赖 border_town_tavern 的 demo 段）：

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS。若 `test_world_model_time` 中用 border_town_tavern 的用例因段名变化失败，需检查：本计划 time 测试用 `load_script("border_town_tavern")` 但断言默认段名 `morning`/`noon`——demo 改成中文名后会失败。**因此在 Task 3 之前需把 time 测试改用 `load_script("tomb_entrance")` 或独立 script，避免段名耦合。** 见 Step 3b。

**Step 3b（必要调整）**：`tests/test_world_model_time.py` 中所有用 `load_script("border_town_tavern")` 且断言 `morning`/`noon`/`evening`/`night`/`deep_night` 的测试，改为用 `tomb_entrance`（无 demo 配置，走默认段）。具体：`WorldClockStateTest`、`TimePhaseTriggerTest`、`TimePhaseLLMTest`、`TimeIntegrationTest` 的 setUp/`load_script` 参数从 `border_town_tavern` 改为 `tomb_entrance`；`test_wait_turn_advances_clock` 的 `noon` 断言保持（tomb_entrance 无 demo，默认段仍含 noon）。`test_talk_records_history_without_double_delta`（favorability 测试）用 border_town_tavern 且不依赖段名——保持不动。

- [ ] **Step 5: Commit**

```bash
git add diceflow/content/scripts/border_town_tavern.yaml diceflow/content/worlds/border_town_tavern/bootstrap.yaml tests/test_world_model_web.py tests/test_world_model_time.py
git commit -m "feat(content): border_town_tavern demo world_model config

Demonstrates per-world customization of time segments and favorability
thresholds. Time tests moved off border_town_tavern to avoid segment-name
coupling."
```

---

### Task 4: Web `StatusData.world_clock` + 关系历史计数

**Files:**
- Modify: `diceflow/web/server.py`（`StatusData`、`_build_status`、`_entity_record`）
- Test: `tests/test_world_model_web.py`

**Interfaces:**
- Produces：`StatusData.world_clock`；每 NPC 实体记录含 `relationship_history_count`。前端可读。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_web.py`:

```python
from diceflow.web.server import app
from fastapi.testclient import TestClient


class WebWorldClockTest(unittest.TestCase):
    def test_status_exposes_world_clock(self) -> None:
        client = TestClient(app)
        sid = client.post("/api/sessions", json={"world_id": "border_town_tavern", "use_llm": False}).json()["session_id"]
        status = client.post(f"/api/sessions/{sid}/turns", json={"input": "等待", "forced_roll": 15}).json()["status"]
        self.assertIn("world_clock", status)
        self.assertEqual(status["world_clock"]["segment"], "正午")  # 清晨+1

    def test_entity_record_has_relationship_history_count(self) -> None:
        client = TestClient(app)
        sid = client.post("/api/sessions", json={"world_id": "border_town_tavern", "use_llm": False}).json()["session_id"]
        client.post(f"/api/sessions/{sid}/turns", json={"input": "和老板说话", "forced_roll": 15})
        status = client.get(f"/api/sessions/{sid}").json()["status"]
        keeper = next(e for e in status["known_entities"] if e["id"] == "barkeeper")
        self.assertEqual(keeper.get("relationship_history_count"), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py -q`
Expected: FAIL — `status` 无 `world_clock` 键 / 实体无 `relationship_history_count`。

- [ ] **Step 3: Write minimal implementation**

`server.py` `StatusData` 加字段（紧接 `ending: str | None = None` 之后）：

```python
    world_clock: dict[str, Any] = Field(default_factory=dict)
```

`_build_status` 返回 `StatusData(...)` 调用中加（紧接 `ending=...` 之前或之后）：

```python
        world_clock=dict(state.world_clock),
```

`_entity_record` 返回 dict 中加（紧接 `"can_edit": ...` 之后）：

```python
        "relationship_history_count": len(
            (ent.get("relationship") or {}).get("history", [])
        ) if isinstance(ent.get("relationship"), dict) else 0,
```

`_build_known_entities` 中为已移除实体构造的 minimal record 也加 `"relationship_history_count": 0`（保持字段存在，避免前端 undefined）。

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_world_model_web.py -q`
Expected: PASS。

Full regression:

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest -q`
Expected: PASS（340 + 新增）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/web/server.py tests/test_world_model_web.py
git commit -m "feat(web): expose world_clock and relationship history count in status"
```

---

### Task 5: 前端状态栏显示时段/天数（手动验证）

**Files:**
- Modify: `web/src/components/StatusSidebar.jsx`

**Interfaces:**
- Produces：状态区显示 `🗓 第N天 · 时段`。

- [ ] **Step 1: 实现**

在 `StatusSidebar.jsx` 的"状态" `AccordionSection` 内，HP 文本之后加：

```jsx
        {status.world_clock && (
          <div className="scene-desc" style={{ marginTop: 4 }}>
            🗓 第{status.world_clock.day}天 · {status.world_clock.segment}
            {status.world_clock.weather ? ` · ${status.world_clock.weather}` : ''}
          </div>
        )}
```

- [ ] **Step 2: 手动验证（构建通过）**

Run: `npm --prefix web run build`
Expected: 构建成功（无 JSX 语法错误）。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/StatusSidebar.jsx
git commit -m "feat(web): show world day/segment in status sidebar"
```

---

## Self-Review（计划自审）

**1. Spec coverage**（对照设计文档 §6.6、§6.7 步骤 6-7）：
- §6.6 `StatusData.world_clock`/`relationship` 摘要 → Task 4 ✓
- §6.6 前端最小展示 → Task 5 ✓
- §6.7 步骤 7 demo 世界配置 → Task 3 ✓
- WorldBootstrap 透传（支撑 web 流程的"随用随改"）→ Task 2 ✓（spec 未显式列但属必要支撑）
- validation 放行（支撑 scripts 流程）→ Task 1 ✓（必要支撑）

**2. Placeholder scan**：无 TBD；代码步骤完整。Task 3 Step 3b 是必要测试解耦，已写出具体改动。

**3. Type consistency**：`world_clock` 形状 `{day,segment,weather}` 各处一致；`world_model` 形状 `{time, favorability}` 与 schemas 默认一致；`relationship_history_count` int。

无类型/命名不一致。
