from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.models import Action
from diceflow.scripting.scene_rules import matches_when


GENERIC_RULE_META_KEYS = {"id", "when"}


def resolve_generic_action_spec(action: Action, state: Any) -> dict[str, Any]:
    for rule in state.script.get("generic_rules", []):
        if matches_when(rule.get("when", {}), action, state):
            return {
                key: deepcopy(value)
                for key, value in rule.items()
                if key not in GENERIC_RULE_META_KEYS
            }
    return {}
