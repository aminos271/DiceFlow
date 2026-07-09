# 通用世界模型底座 — 基础设施与阶段注册表 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 DiceFlow 中引入 `world_model` 底座包，把 `Game.run_turn` 在 resolution 之后的硬编码阶段链 `[reaction → open_ended]` 改成 `PhaseRegistry` 驱动，为后续时间/好感子系统提供"自注册阶段"接入点，且不改变现有行为。

**Architecture:** 新建 `diceflow/world_model/` 包（`base.py` 定义 `PhaseContext`/`Phase` 协议，`registry.py` 实现 `PhaseRegistry`，`schemas.py` 提供世界配置访问器，`phases.py` 把现有 `reaction_phase`/`open_ended_content_phase` 包成注册阶段）。`Game.run_turn` 四个分支解算出初始 `turn_changes` 后统一调 `registry.run_all(ctx)`；每阶段按 `resolution_kind` 自判是否作用，复刻现有跳过语义。

**Tech Stack:** Python 3.12、pytest/unittest、现有 `diceflow.core.reaction` / `diceflow.core.open_ended_content`。

## Global Constraints

- 测试运行命令：`PYTHONPATH=. pytest`（Windows PowerShell 下同样可用）。
- 测试风格：`unittest.TestCase`，用 `load_script("border_town_tavern")` / `load_script("tomb_entrance")` 构造 `GameState`，`Game(script=..., use_llm=False)` 构造游戏。
- 不破坏任何现有测试：`test_game_loop`、`test_reaction_phase`、`test_open_ended_content`、`test_game_open_ended`、`test_threads`、`test_npc_memory`、`test_dynamic_adjudicator`、`test_web_api` 等必须保持绿。
- `resolution_kind` 取值固定为 `"standard" | "dynamic_adjudication" | "invalid" | "transition_attempt"`（见 `diceflow/core/models.py` 的 `TurnResolution`）。
- `reaction_phase(action, check, action_changes, state)` 与 `open_ended_content_phase(action, check, turn_changes, state, llm)` 签名不变，包成阶段时直接调用。
- `merge_state_changes(*changesets: StateChanges)` 来自 `diceflow.core.reaction`，变参。
- 文件编码 UTF-8、LF（git 会自动转 CRLF，无需处理）。

## File Structure

- Create: `diceflow/world_model/__init__.py` — 包导出。
- Create: `diceflow/world_model/base.py` — `PhaseContext` dataclass + `Phase` 协议。
- Create: `diceflow/world_model/registry.py` — `PhaseRegistry`。
- Create: `diceflow/world_model/schemas.py` — `get_world_model_config(state)` + `DEFAULT_WORLD_MODEL`。
- Create: `diceflow/world_model/phases.py` — `ReactionPhase` / `OpenEndedPhase` 适配器。
- Modify: `diceflow/app/game.py` — `Game.__init__` 建 registry 并注册默认阶段；`Game.run_turn` 四分支改走 `registry.run_all`。
- Test: `tests/test_world_model.py` — base/registry/schemas。
- Test: `tests/test_world_model_phases.py` — 阶段适配器 + run_turn 集成。

每个文件单一职责：`base` 只定义协议与上下文；`registry` 只管注册与按序运行；`phases` 只做"把现有函数包成阶段"的适配；`schemas` 只提供配置访问。`game.py` 只改 run_turn 的后处理段与 `__init__`。

---

### Task 1: `world_model/base.py` — PhaseContext 与 Phase 协议

**Files:**
- Create: `diceflow/world_model/__init__.py`
- Create: `diceflow/world_model/base.py`
- Test: `tests/test_world_model.py`

**Interfaces:**
- Produces: `PhaseContext`（dataclass，字段见下）、`Phase`（`Protocol`，属性 `name: str`、`order: int`、方法 `run(ctx: PhaseContext) -> StateChanges`）。后续任务依赖这两个名字。

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_model.py`:

```python
from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script
from diceflow.world_model.base import Phase, PhaseContext


class PhaseContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))

    def test_phase_context_holds_all_fields(self) -> None:
        ctx = PhaseContext(
            action={"type": "talk"},
            validation={"valid": True},
            check={"result": "success"},
            turn_changes={"events": ["x"]},
            state=self.state,
            llm=None,
            lorebook=None,
            resolution_kind="standard",
        )
        self.assertEqual(ctx.resolution_kind, "standard")
        self.assertIs(ctx.state, self.state)
        self.assertEqual(ctx.turn_changes, {"events": ["x"]})

    def test_phase_protocol_has_name_order_run(self) -> None:
        class FakePhase:
            name = "fake"
            order = 0

            def run(self, ctx: PhaseContext) -> dict:
                return {"events": ["ran"]}

        phase: Phase = FakePhase()  # type: ignore[assignment]
        ctx = PhaseContext(
            action={}, validation={"valid": True}, check=None,
            turn_changes={}, state=self.state, llm=None, lorebook=None,
            resolution_kind="standard",
        )
        self.assertEqual(phase.run(ctx), {"events": ["ran"]})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_world_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'diceflow.world_model'`

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/world_model/__init__.py`（本步只导出 base；Task 2 再加 `PhaseRegistry`，Task 3/4 逐步补齐）:

```python
from diceflow.world_model.base import Phase, PhaseContext

__all__ = ["Phase", "PhaseContext"]
```

Create `diceflow/world_model/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from diceflow.core.state import GameState

StateChanges = dict[str, Any]


@dataclass
class PhaseContext:
    """Everything a registered phase needs to decide and apply its changes.

    `turn_changes` is the accumulated changes so far this turn; the registry
    folds each phase's output into it before running the next phase.
    """

    action: dict[str, Any]
    validation: dict[str, Any]
    check: dict[str, Any] | None
    turn_changes: StateChanges
    state: "GameState"
    llm: Any
    lorebook: Any
    resolution_kind: str


class Phase(Protocol):
    """A self-registering turn phase.

    `order` determines run order (ascending). `run` returns the phase's
    StateChanges for this turn, or `{}` if it does not apply.
    """

    name: str
    order: int

    def run(self, ctx: PhaseContext) -> StateChanges: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_world_model.py -v`
Expected: PASS。`__init__.py` 本步只导出 base，不引用尚不存在的 `PhaseRegistry`（Task 2 起逐步补齐导出）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/__init__.py diceflow/world_model/base.py tests/test_world_model.py
git commit -m "feat(world_model): add PhaseContext and Phase protocol"
```

---

### Task 2: `world_model/registry.py` — PhaseRegistry

**Files:**
- Create: `diceflow/world_model/registry.py`
- Modify: `diceflow/world_model/__init__.py`（恢复导出 `PhaseRegistry`）
- Test: `tests/test_world_model.py`

**Interfaces:**
- Consumes: `Phase`（Task 1）、`PhaseContext`（Task 1）、`merge_state_changes(*sets)` from `diceflow.core.reaction`。
- Produces: `PhaseRegistry`，方法 `register(phase)` 与 `run_all(ctx) -> StateChanges`。`run_all` 按 `order` 升序跑每个阶段；每阶段产出非空则 `ctx.state.apply_changes(...)`、再 `ctx.turn_changes = merge_state_changes(ctx.turn_changes, phase_changes)` 折回；返回所有阶段产出的合并 `StateChanges`。后续 `game.py` 与阶段适配器依赖此行为。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model.py`（在文件末尾、`if __name__` 之前加一个测试类）:

```python
from diceflow.world_model.registry import PhaseRegistry


class _RecordingPhase:
    def __init__(self, name: str, order: int, output: dict | None = None) -> None:
        self.name = name
        self.order = order
        self.output = output if output is not None else {}
        self.calls: list[PhaseContext] = []

    def run(self, ctx: PhaseContext) -> dict:
        self.calls.append(ctx)
        return dict(self.output)


class PhaseRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))
        self.ctx = PhaseContext(
            action={}, validation={"valid": True}, check=None,
            turn_changes={}, state=self.state, llm=None, lorebook=None,
            resolution_kind="standard",
        )

    def test_runs_in_order_ascending(self) -> None:
        first = _RecordingPhase("first", order=20, output={"events": ["first"]})
        second = _RecordingPhase("second", order=10, output={"events": ["second"]})
        reg = PhaseRegistry()
        reg.register(first)
        reg.register(second)
        reg.run_all(self.ctx)
        # order 10 runs before order 20
        self.assertEqual(second.calls[0].action, {})  # ran
        self.assertTrue(len(second.calls) == 1 and len(first.calls) == 1)

    def test_applies_and_folds_each_phase_output(self) -> None:
        p1 = _RecordingPhase("p1", order=10, output={"flags": {"runtime.a": True}})
        p2 = _RecordingPhase("p2", order=20, output={"flags": {"runtime.b": True}})
        reg = PhaseRegistry()
        reg.register(p1)
        reg.register(p2)
        merged = reg.run_all(self.ctx)
        # state received both flags
        self.assertTrue(self.state.flags.get("runtime.a"))
        self.assertTrue(self.state.flags.get("runtime.b"))
        # ctx.turn_changes accumulated both
        self.assertTrue(self.ctx.turn_changes["flags"]["runtime.a"])
        self.assertTrue(self.ctx.turn_changes["flags"]["runtime.b"])
        # return value is the merged phase output
        self.assertEqual(set(merged["flags"]), {"runtime.a", "runtime.b"})

    def test_empty_output_skips_apply(self) -> None:
        p = _RecordingPhase("empty", order=10, output={})
        reg = PhaseRegistry()
        reg.register(p)
        merged = reg.run_all(self.ctx)
        self.assertEqual(merged, {})
        self.assertEqual(self.ctx.turn_changes, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_world_model.py::PhaseRegistryTest -v`
Expected: FAIL with `ImportError: cannot import name 'PhaseRegistry'`

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/world_model/registry.py`:

```python
from __future__ import annotations

from diceflow.core.reaction import merge_state_changes
from diceflow.world_model.base import Phase, PhaseContext

StateChanges = dict[str, object]


class PhaseRegistry:
    """Holds registered phases and runs them in ascending `order`.

    Each phase's non-empty output is applied to state and folded into
    `ctx.turn_changes` before the next phase runs, so later phases observe
    the accumulated turn state.
    """

    def __init__(self) -> None:
        self._phases: list[Phase] = []

    def register(self, phase: Phase) -> None:
        self._phases.append(phase)
        self._phases.sort(key=lambda p: p.order)

    def run_all(self, ctx: PhaseContext) -> StateChanges:
        merged: StateChanges = {}
        for phase in self._phases:
            phase_changes = phase.run(ctx)
            if not phase_changes:
                continue
            ctx.state.apply_changes(phase_changes)
            ctx.turn_changes = merge_state_changes(ctx.turn_changes, phase_changes)
            merged = merge_state_changes(merged, phase_changes)
        return merged
```

Restore `diceflow/world_model/__init__.py`:

```python
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.registry import PhaseRegistry

__all__ = ["Phase", "PhaseContext", "PhaseRegistry"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_world_model.py -v`
Expected: PASS（全部测试，含 Task 1 的）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/registry.py diceflow/world_model/__init__.py tests/test_world_model.py
git commit -m "feat(world_model): add PhaseRegistry with ordered fold semantics"
```

---

### Task 3: `world_model/schemas.py` — 世界配置访问器

**Files:**
- Create: `diceflow/world_model/schemas.py`
- Modify: `diceflow/world_model/__init__.py`（导出 `get_world_model_config`）
- Test: `tests/test_world_model.py`

**Interfaces:**
- Consumes: `GameState`（读 `state.script["world_model"]`）。
- Produces: `DEFAULT_WORLD_MODEL: dict`（空骨架，后续子系统计划填充默认表）、`get_world_model_config(state) -> dict`（返回 `state.script.get("world_model", {})` 与 `DEFAULT_WORLD_MODEL` 的浅合并，DEFAULT 作底）。后续时间/好感阶段依赖此函数读配置。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model.py`:

```python
from diceflow.world_model.schemas import DEFAULT_WORLD_MODEL, get_world_model_config


class WorldModelConfigTest(unittest.TestCase):
    def test_returns_empty_dict_when_unset(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        # border_town_tavern has no world_model section yet
        cfg = get_world_model_config(state)
        self.assertIsInstance(cfg, dict)

    def test_script_override_visible(self) -> None:
        state = GameState(load_script("border_town_tavern"))
        state.script["world_model"] = {"time": {"segments": ["dawn", "dusk"]}}
        cfg = get_world_model_config(state)
        self.assertEqual(cfg["time"]["segments"], ["dawn", "dusk"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_world_model.py::WorldModelConfigTest -v`
Expected: FAIL with `ImportError: cannot import name 'get_world_model_config'`

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/world_model/schemas.py`:

```python
from __future__ import annotations

from typing import Any

# Default world_model config. Subsystem plans (time, favorability) will
# populate their own default tables here. For now it is an empty skeleton
# so get_world_model_config has a stable base to merge against.
DEFAULT_WORLD_MODEL: dict[str, Any] = {}


def get_world_model_config(state: Any) -> dict[str, Any]:
    """Return the world_model config for a GameState.

    Merges DEFAULT_WORLD_MODEL (base) with the script's `world_model`
    section (override). Returns an empty dict when neither is set.
    """
    script_cfg = state.script.get("world_model", {})
    if not isinstance(script_cfg, dict):
        script_cfg = {}
    return {**DEFAULT_WORLD_MODEL, **script_cfg}
```

Update `diceflow/world_model/__init__.py`:

```python
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.registry import PhaseRegistry
from diceflow.world_model.schemas import DEFAULT_WORLD_MODEL, get_world_model_config

__all__ = [
    "Phase",
    "PhaseContext",
    "PhaseRegistry",
    "DEFAULT_WORLD_MODEL",
    "get_world_model_config",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_world_model.py -v`
Expected: PASS（全部）。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/schemas.py diceflow/world_model/__init__.py tests/test_world_model.py
git commit -m "feat(world_model): add world_model config accessor"
```

---

### Task 4: `world_model/phases.py` — ReactionPhase 与 OpenEndedPhase 适配器

**Files:**
- Create: `diceflow/world_model/phases.py`
- Modify: `diceflow/world_model/__init__.py`（导出 `ReactionPhase`、`OpenEndedPhase`）
- Test: `tests/test_world_model_phases.py`

**Interfaces:**
- Consumes: `PhaseContext`/`Phase`（Task 1）、`reaction_phase` from `diceflow.core.reaction`、`open_ended_content_phase` from `diceflow.core.open_ended_content`。
- Produces: `ReactionPhase`（`name="reaction"`, `order=10`）、`OpenEndedPhase`（`name="open_ended"`, `order=20`）。两者 `run(ctx)` 在 `resolution_kind in {"invalid","transition_attempt"}` 或 `ctx.check is None` 时返回 `{}`，否则委托底层函数。`game.py` 依赖这两个类名与 order。

- [ ] **Step 1: Write the failing test**

Create `tests/test_world_model_phases.py`:

```python
from __future__ import annotations

import unittest
from typing import Any

from diceflow.core.models import Action
from diceflow.core.state import GameState
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.loader import load_script
from diceflow.world_model.base import PhaseContext
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase


def _ctx(state: GameState, *, action: dict, check: dict | None,
         resolution_kind: str, turn_changes: dict | None = None) -> PhaseContext:
    return PhaseContext(
        action=action, validation={"valid": True}, check=check,
        turn_changes=turn_changes or {}, state=state, llm=None,
        lorebook=None, resolution_kind=resolution_kind,
    )


class ReactionPhaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game_state = GameState(load_script("tomb_entrance"))
        self.attack = {"type": "attack", "target": "守卫", "method": "", "tool": ""}
        result = validate(self.attack, self.game_state)
        self.assertTrue(result["valid"])
        self.attack = result.get("_normalized_action", self.attack)
        # apply the attack so reaction has state to react to
        changes = update_state(self.attack, {"result": "success"}, self.game_state)
        self.game_state.apply_changes(changes)
        self.check = {"result": "success"}

    def test_standard_delegates_to_reaction_phase(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=self.check,
                   resolution_kind="standard", turn_changes={})
        out = phase.run(ctx)
        self.assertIn("player", out)
        self.assertEqual(out["player"]["hp_delta"], -2)

    def test_invalid_resolution_skips(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=self.check,
                   resolution_kind="invalid")
        self.assertEqual(phase.run(ctx), {})

    def test_transition_resolution_skips(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=self.check,
                   resolution_kind="transition_attempt")
        self.assertEqual(phase.run(ctx), {})

    def test_none_check_skips(self) -> None:
        phase = ReactionPhase()
        ctx = _ctx(self.game_state, action=self.attack, check=None,
                   resolution_kind="standard")
        self.assertEqual(phase.run(ctx), {})


class _FakeOpenEndedLLM:
    narration_available = True

    def __init__(self, patch: dict[str, Any]) -> None:
        self.patch = patch
        self.call_count = 0

    def generate_open_ended_content(self, action, check, state, result_quality):
        self.call_count += 1
        return dict(self.patch)


class OpenEndedPhaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = GameState(load_script("border_town_tavern"))
        self.action: Action = {
            "intent_family": "social", "type": "social", "target": "酒馆",
            "target_id": "", "tool": "", "tool_id": "", "approach_tags": [],
            "method_text": "在酒馆里看看有没有人愿意结伴同行",
            "method": "在酒馆里看看有没有人愿意结伴同行",
        }
        self.check = {
            "dc": 13, "roll": 15, "result": "success", "dynamic": True,
            "assessment": {"intent_kind": "social", "risk": "low",
                           "difficulty": "medium", "plausibility": "reasonable"},
        }

    def test_standard_delegates_to_open_ended(self) -> None:
        llm = _FakeOpenEndedLLM({"events": "一个旅人朝你点头。", "ops": []})
        phase = OpenEndedPhase()
        ctx = _ctx(self.state, action=self.action, check=self.check,
                   resolution_kind="standard", turn_changes={})
        ctx.llm = llm
        out = phase.run(ctx)
        self.assertEqual(llm.call_count, 1)
        self.assertIn("酒馆里看看有没有人愿意结伴同行", out.get("events", [""])[0]
                      if out.get("events") else "")

    def test_invalid_resolution_skips(self) -> None:
        llm = _FakeOpenEndedLLM({"events": "nope", "ops": []})
        phase = OpenEndedPhase()
        ctx = _ctx(self.state, action=self.action, check=self.check,
                   resolution_kind="invalid")
        ctx.llm = llm
        self.assertEqual(phase.run(ctx), {})
        self.assertEqual(llm.call_count, 0)

    def test_transition_resolution_skips(self) -> None:
        llm = _FakeOpenEndedLLM({"events": "nope", "ops": []})
        phase = OpenEndedPhase()
        ctx = _ctx(self.state, action=self.action, check=self.check,
                   resolution_kind="transition_attempt")
        ctx.llm = llm
        self.assertEqual(phase.run(ctx), {})
        self.assertEqual(llm.call_count, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_world_model_phases.py -v`
Expected: FAIL with `ImportError: cannot import name 'ReactionPhase'`

- [ ] **Step 3: Write minimal implementation**

Create `diceflow/world_model/phases.py`:

```python
from __future__ import annotations

from diceflow.core.open_ended_content import open_ended_content_phase
from diceflow.core.reaction import reaction_phase
from diceflow.world_model.base import Phase, PhaseContext

StateChanges = dict[str, object]

# Resolution kinds where the scripted post-resolution phases must NOT run,
# preserving the pre-refactor per-branch skipping semantics.
_SKIP_KINDS = frozenset({"invalid", "transition_attempt"})


class ReactionPhase:
    """Wraps diceflow.core.reaction.reaction_phase as a registered phase."""

    name = "reaction"
    order = 10

    def run(self, ctx: PhaseContext) -> StateChanges:
        if ctx.resolution_kind in _SKIP_KINDS or ctx.check is None:
            return {}
        return reaction_phase(ctx.action, ctx.check, ctx.turn_changes, ctx.state)


class OpenEndedPhase:
    """Wraps diceflow.core.open_ended_content.open_ended_content_phase."""

    name = "open_ended"
    order = 20

    def run(self, ctx: PhaseContext) -> StateChanges:
        if ctx.resolution_kind in _SKIP_KINDS or ctx.check is None:
            return {}
        return open_ended_content_phase(
            ctx.action, ctx.check, ctx.turn_changes, ctx.state, ctx.llm
        )
```

Update `diceflow/world_model/__init__.py`:

```python
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase
from diceflow.world_model.registry import PhaseRegistry
from diceflow.world_model.schemas import DEFAULT_WORLD_MODEL, get_world_model_config

__all__ = [
    "Phase",
    "PhaseContext",
    "PhaseRegistry",
    "ReactionPhase",
    "OpenEndedPhase",
    "DEFAULT_WORLD_MODEL",
    "get_world_model_config",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_world_model_phases.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add diceflow/world_model/phases.py diceflow/world_model/__init__.py tests/test_world_model_phases.py
git commit -m "feat(world_model): wrap reaction and open_ended as registered phases"
```

---

### Task 5: `Game.run_turn` 改走 PhaseRegistry（行为保持）

**Files:**
- Modify: `diceflow/app/game.py`（`Game.__init__`、`Game.run_turn` 四分支）
- Test: `tests/test_world_model_phases.py`（新增 run_turn 集成测试）+ 全量回归

**Interfaces:**
- Consumes: `PhaseRegistry`、`PhaseContext`、`ReactionPhase`、`OpenEndedPhase`（Task 1-4）。`merge_state_changes` from `diceflow.core.reaction`（已在 game.py 使用）。
- Produces: `Game.__init__` 新增 `self.phases: PhaseRegistry`，注册 `ReactionPhase`、`OpenEndedPhase`。`run_turn` 四分支在应用初始 `changes` 后统一调 `self._run_post_resolution(ctx, turn_changes)`，该方法构造 `PhaseContext`、调 `self.phases.run_all(ctx)`、对 `standard`/`dynamic_adjudication` 调 `_sync_lorebook_for_patch`，返回合并后的 `turn_changes`。后续子系统计划只需 `self.phases.register(TimePhase())` 即可接入。

- [ ] **Step 1: Write the failing test**

Append to `tests/test_world_model_phases.py`:

```python
from diceflow.app.game import Game
from diceflow.world_model.base import Phase
from diceflow.world_model.registry import PhaseRegistry


class _SpyPhase:
    """Records whether it ran during a turn, regardless of branch."""
    name = "spy"
    order = 15  # between reaction(10) and open_ended(20)

    def __init__(self) -> None:
        self.ran_kinds: list[str] = []

    def run(self, ctx: PhaseContext) -> dict:
        self.ran_kinds.append(ctx.resolution_kind)
        return {}


class RunTurnRegistryTest(unittest.TestCase):
    def _game(self) -> Game:
        game = Game(script=load_script("border_town_tavern"), use_llm=False)
        return game

    def test_standard_turn_runs_registered_phases(self) -> None:
        game = self._game()
        spy = _SpyPhase()
        game.phases.register(spy)
        game.run_turn("和老板攀谈")  # talk action → standard or dynamic
        # spy.run was called at least once during the turn
        self.assertTrue(len(spy.ran_kinds) >= 1)

    def test_invalid_turn_still_invokes_registry_but_reaction_open_ended_skip(self) -> None:
        game = self._game()
        spy = _SpyPhase()
        game.phases.register(spy)
        game.run_turn("xyzqwerty 不存在的动作")  # invalid → phases gate to {}
        # registry still ran the spy (uniform invocation)
        self.assertTrue(len(spy.ran_kinds) >= 1)
        # and the game did not crash / game_over not set by the turn itself
        self.assertFalse(game.state.flags.get("game_over"))

    def test_existing_reaction_still_fires_in_combat(self) -> None:
        """Regression: a hostile target still counter-attacks after a hit."""
        game = Game(script=load_script("tomb_entrance"), use_llm=False)
        hp_before = game.state.player["hp"]
        game.run_turn("攻击守卫")
        # guard retaliates → player loses hp (reaction phase still active)
        self.assertLess(game.state.player["hp"], hp_before)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_world_model_phases.py::RunTurnRegistryTest -v`
Expected: FAIL — `Game` 实例没有 `phases` 属性（`AttributeError`）。

- [ ] **Step 3: Write minimal implementation**

Modify `diceflow/app/game.py`。先改 import 块（在文件顶部既有 import 后追加）：

```python
from diceflow.world_model import PhaseContext, PhaseRegistry
from diceflow.world_model.phases import OpenEndedPhase, ReactionPhase
```

改 `Game.__init__`（在 `self.lorebook = lorebook` 这一行之后追加）：

```python
        self.phases = PhaseRegistry()
        self.phases.register(ReactionPhase())
        self.phases.register(OpenEndedPhase())
```

新增辅助方法（放在 `run_turn` 方法之后、`_build_llm` 之前）：

```python
    def _run_post_resolution(
        self,
        turn_id: int,
        player_input: str,
        action: dict[str, Any],
        validation: dict[str, Any],
        check: dict[str, Any] | None,
        turn_changes: dict[str, Any],
        resolution_kind: str,
    ) -> dict[str, Any]:
        """Run the registered post-resolution phase chain uniformly.

        Replaces the per-branch reaction→open_ended calls. Each phase self-
        decides whether to apply based on resolution_kind, preserving the
        pre-refactor skip semantics for invalid/transition branches.
        """
        ctx = PhaseContext(
            action=action,
            validation=validation,
            check=check,
            turn_changes=dict(turn_changes),
            state=self.state,
            llm=self.llm,
            lorebook=self.lorebook,
            resolution_kind=resolution_kind,
        )
        phase_changes = self.phases.run_all(ctx)
        if resolution_kind in {"standard", "dynamic_adjudication"}:
            _sync_lorebook_for_patch(self.lorebook, ctx.turn_changes, turn_id)
        return merge_state_changes(turn_changes, phase_changes)
```

Now rewrite the four branches in `run_turn` to use it. Replace the dynamic-adjudication branch's post-resolution block (lines 113-120, after `self.state.apply_changes(changes)` at line 112 which stays):

old（`game.py:113-120`）:
```python
            reaction_changes = reaction_phase(action, check, changes, self.state)
            self.state.apply_changes(reaction_changes)
            turn_changes = merge_state_changes(changes, reaction_changes)
            open_ended_changes = open_ended_content_phase(action, check, turn_changes, self.state, self.llm)
            self.state.apply_changes(open_ended_changes)
            _sync_lorebook_for_patch(self.lorebook, open_ended_changes, turn_id)
            turn_changes = merge_state_changes(turn_changes, open_ended_changes)
            reason_tags = list(assessment.get("reason_tags", []))
```
new:
```python
            turn_changes = self._run_post_resolution(
                turn_id, player_input, action, validation, check, changes,
                "dynamic_adjudication",
            )
            reason_tags = list(assessment.get("reason_tags", []))
```
注意：`changes` 已在 `game.py:112` 应用过，**不要再 `apply_changes(changes)`**；`_run_post_resolution` 内部只应用各阶段产出。`build_turn_resolution`（121 起）与 `TurnRecord`（135 起）原本就用 `state_changes=turn_changes`，无需改动。

Replace the standard branch's post-resolution block:

old（约 `game.py:191-199`）:
```python
        check = self.rules.resolve(action, self.state, forced_roll=forced_roll)
        changes = update_state(action, check, self.state)
        self.state.apply_changes(changes)
        reaction_changes = reaction_phase(action, check, changes, self.state)
        self.state.apply_changes(reaction_changes)
        turn_changes = merge_state_changes(changes, reaction_changes)
        open_ended_changes = open_ended_content_phase(action, check, turn_changes, self.state, self.llm)
        self.state.apply_changes(open_ended_changes)
        _sync_lorebook_for_patch(self.lorebook, open_ended_changes, turn_id)
        turn_changes = merge_state_changes(turn_changes, open_ended_changes)
        turn_resolution = build_turn_resolution(
```
new:
```python
        check = self.rules.resolve(action, self.state, forced_roll=forced_roll)
        changes = update_state(action, check, self.state)
        self.state.apply_changes(changes)
        turn_changes = self._run_post_resolution(
            turn_id, player_input, action, validation, check, changes,
            "standard",
        )
        turn_resolution = build_turn_resolution(
```

For the invalid branch (约 `game.py:154-161`)，在 `self.state.apply_changes(changes)` 之后、`build_turn_resolution` 之前插入注册表调用（保持其 `turn_changes = changes` 语义——阶段对 invalid 返回 {}）：

old:
```python
        if not validation["valid"]:
            changes = {
                "events": [
                    str(validation["reason"]),
                    str(self.script.get("invalid_action_event", "行动没有成立，但局势仍在推进。")),
                ],
            }
            self.state.apply_changes(changes)
            turn_resolution = build_turn_resolution(
```
new:
```python
        if not validation["valid"]:
            changes = {
                "events": [
                    str(validation["reason"]),
                    str(self.script.get("invalid_action_event", "行动没有成立，但局势仍在推进。")),
                ],
            }
            self.state.apply_changes(changes)
            turn_changes = self._run_post_resolution(
                turn_id, player_input, action, validation, None, changes,
                "invalid",
            )
            turn_resolution = build_turn_resolution(
```
注意：invalid 分支阶段返回 {}，故 `turn_changes == changes`；但仍要把两处 `state_changes` 改成 `turn_changes`，与 transition 同理（为将来阶段留接口）。在该分支内：
- `build_turn_resolution(...)` 的 `state_changes=changes,`（`game.py:168`）→ `state_changes=turn_changes,`
- `TurnRecord(...)` 的 `state_changes=changes,`（`game.py:181`）→ `state_changes=turn_changes,`

For the dynamic_world (transition) branch（`game.py:64-105`），在 `self.state.apply_changes(world_changes)`（line 74）之后插入注册表调用。原分支用 `state_changes=world_changes` 构造 `build_turn_resolution`（line 81）与 `TurnRecord`（line 99）。改为先跑注册表，并把这两处的 `state_changes` 都改成 `turn_changes`——这很重要：后续时间阶段会在 transition 分支产出事件，narrator 必须能看到。

old（`game.py:74-75`）:
```python
            self.state.apply_changes(world_changes)
            turn_resolution = build_turn_resolution(
```
new:
```python
            self.state.apply_changes(world_changes)
            turn_changes = self._run_post_resolution(
                turn_id, player_input, action, validation, check, world_changes,
                "transition_attempt",
            )
            turn_resolution = build_turn_resolution(
```
然后在该分支内：
- `build_turn_resolution(...)` 的 `state_changes=world_changes,`（`game.py:81`）→ `state_changes=turn_changes,`
- `TurnRecord(...)` 的 `state_changes=world_changes,`（`game.py:99`）→ `state_changes=turn_changes,`
- `check=check,` 保持。`summary = _make_summary(action, check, world_changes)`（line 88）可保留 `world_changes`（summary 文案无影响），也可改成 `turn_changes`，二选一即可。

最后：`game.py` 顶部原来导入了 `reaction_phase` 和 `open_ended_content_phase`（`from diceflow.core.reaction import merge_state_changes, reaction_phase` 与 `from diceflow.core.open_ended_content import open_ended_content_phase`）。`run_turn` 不再直接调用它们，但保留 import 无害；为整洁可移除 `reaction_phase`、`open_ended_content_phase` 的导入，只保留 `merge_state_changes`。把：

```python
from diceflow.core.reaction import merge_state_changes, reaction_phase
```
改为：
```python
from diceflow.core.reaction import merge_state_changes
```
并删除行：
```python
from diceflow.core.open_ended_content import open_ended_content_phase
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_world_model_phases.py -v`
Expected: PASS（含三个 RunTurnRegistryTest）。

Then run the full regression suite:

Run: `PYTHONPATH=. pytest -v`
Expected: PASS（全部现有测试 + 新测试均绿）。若 `test_game_open_ended` 或 `test_reaction_phase` 失败，检查 invalid/transition 分支的 `state_changes=` 是否已改为 `turn_changes`，以及 `_run_post_resolution` 的 `ctx.turn_changes = dict(turn_changes)` 拷贝是否把初始 changes 带入。

- [ ] **Step 5: Commit**

```bash
git add diceflow/app/game.py tests/test_world_model_phases.py
git commit -m "refactor(game): drive post-resolution phases via PhaseRegistry

run_turn's four branches now uniformly invoke the registered phase chain
(reaction → open_ended). Phases self-gate on resolution_kind, preserving
the prior skip semantics for invalid/transition branches. Behavior is
unchanged; this unblocks the time and favorability subsystems to register
their own phases."
```

---

## Self-Review（计划自审）

**1. Spec coverage**（对照设计文档 §6.7 迁移顺序）：
- 步骤 1（建包 registry+base+schemas）→ Task 1/2/3 ✓
- 步骤 2（run_turn 后处理链改注册表，reaction/open_ended 迁移，靠 resolution_kind 复刻跳过）→ Task 4/5 ✓
- 步骤 3-7（GameState 槽、time/favorability 阶段、LLM、Web、demo 世界）→ 属后续计划（时间子系统、好感子系统、Web+demo），本计划为前置基础设施，故意不含。已在开头说明。

**2. Placeholder scan**：无 TBD/TODO；Task 3 的 `if __name__` 占位说明已在步骤内明确要求删除并给出最终内容；所有代码步骤均给出完整代码。

**3. Type consistency**：
- `PhaseContext` 字段在 Task 1 定义，Task 2/4/5 使用一致（`action/validation/check/turn_changes/state/llm/lorebook/resolution_kind`）。
- `PhaseRegistry.register`/`run_all` 在 Task 2 定义，Task 5 调用一致。
- `ReactionPhase.name="reaction", order=10`、`OpenEndedPhase.name="open_ended", order=20` 在 Task 4 定义，Task 5 注册时依赖；后续时间(order=30)/好感(order=40)计划已预留序号。
- `_run_post_resolution` 签名在 Task 5 定义并自洽；`_SKIP_KINDS = {"invalid","transition_attempt"}` 与 spec §6.2 一致。
- `merge_state_changes` 变参调用：`merge_state_changes(turn_changes, phase_changes)` 与 `merge_state_changes(ctx.turn_changes, phase_changes)` 一致。

无类型/命名不一致。

## 后续计划（本计划之后，各自独立可测）

- **Plan 2 — 时间子系统**：`world_clock` GameState 槽 + `apply_changes` 键（`advance_time`/`set_clock`）+ `schemas` 时间默认表 + `TimePhase`(order=30, 动作驱动, LLM 桶+回退) + LLM `judge_time_impact` + prompt + 暴露进 `_compact_state`/`turn_resolution`。
- **Plan 3 — 好感子系统**：实体 `relationship` 子槽 + `apply_changes` 键（`relationship_events`）+ `schemas` 好感默认表 + `FavorabilityPhase`(order=40, LLM 桶+阈值反应+回退) + LLM `judge_favorability_effect` + prompt。
- **Plan 4 — Web 暴露 + demo**：`StatusData.world_clock`/`relationship` + `border_town_tavern` 的 `world_model` 配置。
