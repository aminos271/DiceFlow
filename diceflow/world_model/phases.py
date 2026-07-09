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
