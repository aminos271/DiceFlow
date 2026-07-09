from __future__ import annotations

from diceflow.core.reaction import merge_state_changes
from diceflow.world_model.base import Phase, PhaseContext

StateChanges = dict[str, object]


class PhaseRegistry:
    """Holds registered phases and runs them in ascending ``order``.

    Each phase's non-empty output is applied to state and folded into
    ``ctx.turn_changes`` before the next phase runs, so later phases observe
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
