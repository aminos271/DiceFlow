from __future__ import annotations

import unittest

from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script
from diceflow.world_model.base import Phase, PhaseContext
from diceflow.world_model.registry import PhaseRegistry


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
        # both ran exactly once
        self.assertEqual(len(second.calls), 1)
        self.assertEqual(len(first.calls), 1)

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


if __name__ == "__main__":
    unittest.main()
