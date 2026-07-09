from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from diceflow.core.state import GameState

StateChanges = dict[str, Any]


@dataclass
class PhaseContext:
    """Everything a registered phase needs to decide and apply its changes.

    ``turn_changes`` is the accumulated changes so far this turn; the registry
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

    ``order`` determines run order (ascending). ``run`` returns the phase's
    StateChanges for this turn, or ``{}`` if it does not apply.
    """

    name: str
    order: int

    def run(self, ctx: PhaseContext) -> StateChanges: ...
