from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.matching import matches_all_tags, matches_any_tag, matches_value
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState
from diceflow.core.utils import traverse_replace
from diceflow.scripting.scene_rules import matches_when


REACTION_WHEN_KEYS = {"result", "target_alive", "player_alive", "actor_tags", "any_actor_tags"}


def reaction_phase(
    action: Action,
    check: CheckResult,
    action_changes: StateChanges,
    state: GameState,
) -> StateChanges:
    del action_changes

    if state.flags.get("game_over") or state.player.get("hp", 0) <= 0:
        return {}

    merged: StateChanges = {}
    for rule in state.script.get("reaction_rules", []):
        if not _matches_reaction_rule(rule, action, check, state):
            continue
        for actor_id in _resolve_actors(rule.get("actor", "target"), action, state):
            actor = state.entities.get(actor_id)
            if not _can_react(actor):
                continue
            if not _matches_actor_tags(actor or {}, rule.get("when", {})):
                continue
            changes = _expand_reaction_changes(rule.get("changes", {}), action, actor_id, state)
            merged = merge_state_changes(merged, changes)
    return merged


def merge_state_changes(*changesets: StateChanges) -> StateChanges:
    merged: StateChanges = {}
    for changes in changesets:
        merged = _merge_values(merged, changes)
    return merged


def _matches_reaction_rule(
    rule: object,
    action: Action,
    check: CheckResult,
    state: GameState,
) -> bool:
    if not isinstance(rule, dict):
        return False
    when = rule.get("when", {})
    if not isinstance(when, dict):
        return False

    result = str(check.get("result") or "")
    if "result" in when and not matches_value(result, when["result"]):
        return False

    if "target_alive" in when:
        target = state.entities.get(str(action.get("target_id") or ""), {})
        if bool(target.get("alive", True)) != bool(when["target_alive"]):
            return False

    if "player_alive" in when and (state.player.get("hp", 0) > 0) != bool(when["player_alive"]):
        return False

    base_when = {key: value for key, value in when.items() if key not in REACTION_WHEN_KEYS}
    if base_when and not matches_when(base_when, action, state):
        return False

    return isinstance(rule.get("changes", {}), dict)


def _resolve_actors(selector: object, action: Action, state: GameState) -> list[str]:
    if selector == "target":
        target_id = str(action.get("target_id") or "")
        return [target_id] if target_id in state.entities else []
    if selector == "each_hostile":
        return list(state.get_hostile_entities())
    if selector == "first_hostile":
        return list(state.get_hostile_entities())[:1]
    if isinstance(selector, str) and selector in state.entities:
        return [selector]
    if isinstance(selector, list):
        return [str(actor_id) for actor_id in selector if str(actor_id) in state.entities]
    return []


def _can_react(actor: dict[str, Any] | None) -> bool:
    if not actor:
        return False
    if not actor.get("available", True) or not actor.get("visible", True):
        return False
    return bool(actor.get("alive", True))


def _matches_actor_tags(actor: dict[str, Any], when: object) -> bool:
    if not isinstance(when, dict):
        return True
    tags = actor.get("tags", [])
    if "actor_tags" in when and not matches_all_tags(tags, when["actor_tags"]):
        return False
    if "any_actor_tags" in when and not matches_any_tag(tags, when["any_actor_tags"]):
        return False
    return True


def _expand_reaction_changes(
    changes: StateChanges,
    action: Action,
    actor_id: str,
    state: GameState,
) -> StateChanges:
    return _replace_placeholders(deepcopy(changes), action, actor_id, state)


def _replace_placeholders(value: object, action: Action, actor_id: str, state: GameState) -> Any:
    target_id = str(action.get("target_id") or "")
    actor = state.entities.get(actor_id, {})
    target = state.entities.get(target_id, {})

    if value == "$actor":
        return actor_id
    if value == "$target":
        return target_id or "$target"

    def _leaf(v: object) -> object:
        if isinstance(v, str):
            return (
                v.replace("$actor_name", str(actor.get("name") or actor_id or "actor"))
                .replace("$target_name", str(target.get("name") or action.get("target") or "target"))
                .replace("$action_family", action_family(action))
            )
        return v

    return traverse_replace(value, _leaf)


def _merge_values(left: Any, right: Any) -> Any:
    if not right:
        return deepcopy(left)
    if not left:
        return deepcopy(right)
    if isinstance(left, dict) and isinstance(right, dict):
        merged = deepcopy(left)
        for key, value in right.items():
            if str(key).endswith("_delta") and key in merged:
                merged[key] = merged[key] + value
            else:
                merged[key] = _merge_values(merged.get(key), value)
        return merged
    if isinstance(left, list) and isinstance(right, list):
        return [*deepcopy(left), *deepcopy(right)]
    return deepcopy(right)


