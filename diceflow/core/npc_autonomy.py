from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.reaction import merge_state_changes
from diceflow.core.state import GameState
from diceflow.llm.client import LLMClient

# When False (default), normal turns never call npc_autonomy_phase.
# Set to True via hook or script flag to re-enable for important events.
NPC_AUTONOMY_ENABLED = False

AUTONOMY_COOLDOWN = 2
ALLOWED_CHANGE_KEYS = {"player", "entities", "events", "set_entity_states"}


def npc_autonomy_phase(
    action: Action,
    check: CheckResult | None,
    current_turn_changes: StateChanges,
    state: GameState,
    llm: LLMClient | None,
) -> StateChanges:
    """Select at most one visible NPC to perform a controlled autonomous action.

    Returns a StateChanges dict (events, player deltas, entity changes).
    """
    if state.flags.get("game_over") or state.player.get("hp", 0) <= 0:
        return {}

    npcs = _visible_npcs(state)
    if not npcs:
        return {}

    candidates = _eligible_npcs(npcs, action, state)
    if not candidates:
        return {}

    if llm:
        result = _llm_autonomy(llm, candidates, action, state)
    else:
        result = _deterministic_autonomy(candidates, action, state)

    changes = _clamp_and_filter(result, state)
    actor_id = str(result.get("actor_id") or "")
    if changes and actor_id in state.entities:
        changes.setdefault("set_entity_states", {}).setdefault(actor_id, {})["last_autonomy_turn"] = state.turn_id
    return changes


def _visible_npcs(state: GameState) -> dict[str, dict[str, Any]]:
    """Return visible NPCs that are alive and available."""
    return {
        eid: deepcopy(ent)
        for eid, ent in state.get_visible_entities().items()
        if ent.get("type") == "npc" or "npc" in ent.get("tags", [])
        if ent.get("alive", True)
        if ent.get("available", True)
    }


def _eligible_npcs(
    npcs: dict[str, dict[str, Any]],
    action: Action,
    state: GameState,
) -> dict[str, dict[str, Any]]:
    """Filter NPCs by cooldown and relevance."""
    turn_id = state.turn_id
    eligible: dict[str, dict[str, Any]] = {}
    target_id = str(action.get("target_id") or "")

    for eid, npc in npcs.items():
        if eid == target_id and action_family(action) in {"attack", "talk", "inspect", "use", "open", "take"}:
            continue
        last_turn = npc.get("last_autonomy_turn", 0)
        if isinstance(last_turn, int) and turn_id - last_turn < AUTONOMY_COOLDOWN:
            continue
        eligible[eid] = npc

    # Priority sort: hostile > high favorability > low favorability/suspicious
    def _score(item: tuple[str, dict[str, Any]]) -> int:
        _, npc = item
        if npc.get("hostile") or "hostile" in npc.get("tags", []):
            return 0  # highest priority
        fav = npc.get("favorability", 0)
        if isinstance(fav, (int, float)) and fav >= 2:
            return 1
        disp = npc.get("disposition", "")
        if disp == "suspicious" or (isinstance(fav, (int, float)) and fav <= -2):
            return 2
        return 3  # lowest priority

    sorted_npcs = sorted(eligible.items(), key=_score)
    # Return only the highest priority NPC
    if sorted_npcs:
        return {sorted_npcs[0][0]: sorted_npcs[0][1]}
    return {}


def _deterministic_autonomy(
    npcs: dict[str, dict[str, Any]],
    action: Action,
    state: GameState,
) -> dict[str, Any]:
    """Deterministic fallback when no LLM is available."""
    if not npcs:
        return {}
    eid, npc = next(iter(npcs.items()))
    name = str(npc.get("name") or eid)

    if npc.get("hostile") or "hostile" in npc.get("tags", []):
        # Hostile NPC: apply pressure, warn, or minor damage
        player_hp = state.player.get("hp", 0)
        if player_hp > 2:
            return {
                "actor_id": eid,
                "changes": {
                    "events": [f"{name}冷冷地盯着你，向前逼近了半步。"],
                    "player": {"hp_delta": -1},
                },
            }
        else:
            return {
                "actor_id": eid,
                "changes": {
                    "events": [f"{name}挡在你面前，不给你任何空隙。"],
                },
            }

    fav = npc.get("favorability", 0)
    if isinstance(fav, (int, float)) and fav >= 2:
        return {
            "actor_id": eid,
            "changes": {
                "events": [f"{name}朝你微微点头，低声说了一句提醒的话。"],
            },
        }

    disp = npc.get("disposition", "")
    if disp == "suspicious" or (isinstance(fav, (int, float)) and fav <= -2):
        return {
            "actor_id": eid,
            "changes": {
                "events": [f"{name}冷冷地看了你一眼，没有回应。"],
                "entities": {eid: {"favorability_delta": -1}},
            },
        }

    return {}


def _llm_autonomy(
    llm: LLMClient,
    npcs: dict[str, dict[str, Any]],
    action: Action,
    state: GameState,
) -> dict[str, Any]:
    """Use LLM to determine NPC autonomy."""
    try:
        visible_npcs = {
            eid: {
                k: v for k, v in npc.items()
                if k not in {"aliases", "max_hp", "equipped", "hooks", "metadata", "inventory"}
            }
            for eid, npc in npcs.items()
        }
        result = llm.generate_npc_autonomy(visible_npcs, action, state)
        if isinstance(result, dict) and result.get("actor_id"):
            return result
    except Exception:
        pass
    return _deterministic_autonomy(npcs, action, state)


def _clamp_and_filter(result: dict[str, Any], state: GameState) -> StateChanges:
    """Clamp and sanitize LLM or deterministic output into valid StateChanges."""
    changes = result.get("changes")
    if not isinstance(changes, dict):
        return {}

    sanitized: StateChanges = {}
    for key in ALLOWED_CHANGE_KEYS:
        if key in changes:
            sanitized[key] = deepcopy(changes[key])

    # Clamp player hp_delta
    if "player" in sanitized and isinstance(sanitized["player"], dict):
        hp_delta = sanitized["player"].get("hp_delta", 0)
        if isinstance(hp_delta, (int, float)):
            player_hp = state.player.get("hp", 0)
            # Never kill the player through autonomy
            if hp_delta < 0:
                hp_delta = max(hp_delta, -1)
                if player_hp + hp_delta < 1:
                    hp_delta = 0
            sanitized["player"]["hp_delta"] = int(hp_delta)
        # Strip non-delta player keys
        sanitized["player"] = {
            k: v for k, v in sanitized["player"].items()
            if k.endswith("_delta")
        }

    # Clamp entity changes
    if "entities" in sanitized and isinstance(sanitized["entities"], dict):
        clamped_entities: dict[str, Any] = {}
        for eid, ent_changes in sanitized["entities"].items():
            if not isinstance(ent_changes, dict) or eid not in state.entities:
                continue
            clamped: dict[str, Any] = {}
            for k, v in ent_changes.items():
                if k == "favorability_delta" and isinstance(v, (int, float)):
                    clamped[k] = max(-1, min(1, int(v)))
                elif k.endswith("_delta") and isinstance(v, (int, float)):
                    clamped[k] = int(v)
                elif k == "hostile" and isinstance(v, bool):
                    clamped[k] = v
            if clamped:
                clamped_entities[eid] = clamped
        sanitized["entities"] = clamped_entities

    if "set_entity_states" in sanitized and isinstance(sanitized["set_entity_states"], dict):
        clamped_states: dict[str, Any] = {}
        for eid, ent_changes in sanitized["set_entity_states"].items():
            if not isinstance(ent_changes, dict) or eid not in state.entities:
                continue
            if isinstance(ent_changes.get("last_autonomy_turn"), int):
                clamped_states[eid] = {"last_autonomy_turn": ent_changes["last_autonomy_turn"]}
        sanitized["set_entity_states"] = clamped_states

    # Filter events to strings
    if "events" in sanitized and isinstance(sanitized["events"], list):
        sanitized["events"] = [str(e) for e in sanitized["events"] if e]

    # Strip forbidden keys
    for forbidden in ("spawn_entities", "remove_entities", "runtime_script_patch",
                      "move_item_to_inventory", "reveal_entities"):
        sanitized.pop(forbidden, None)

    return sanitized


# Update last_autonomy_turn on the actual state entities after applying changes.
def record_autonomy_turn(state: GameState, changes: StateChanges) -> None:
    """Set last_autonomy_turn on entities that acted in this autonomy phase."""
    turn_id = state.turn_id
    for eid in changes.get("entities", {}):
        if eid in state.entities:
            state.entities[eid]["last_autonomy_turn"] = turn_id
    for eid in changes.get("set_entity_states", {}):
        if eid in state.entities:
            state.entities[eid]["last_autonomy_turn"] = turn_id
