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
