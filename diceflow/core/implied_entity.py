from __future__ import annotations

from copy import deepcopy
from typing import Any

from diceflow.core.intent import action_family
from diceflow.core.models import Action, StateChanges
from diceflow.core.utils import traverse_replace


PRONOUN_POSSESSIVES = ("他的", "她的", "它的", "其")


def resolve_implied_entity(action: Action, state: Any) -> str:
    target_text = str(action.get("target") or "").strip()
    if not target_text:
        return ""

    for source_id, source in state.entities.items():
        if not state.is_interactable_entity(source_id):
            continue
        for implied in _iter_implied_specs(source, target_text, state):
            template = _resolve_implied_template(implied, state)
            if not template or not template.get("entity"):
                continue
            entity = _render_implied_entity(template, source_id, source, state)
            if not _matches_implied_target(target_text, entity, implied, source):
                continue

            entity_id = _render_source_template(
                str(template.get("id_template") or f"{source_id}_{_implied_kind(implied)}"),
                source_id,
                source,
                state,
            )
            if not entity_id:
                continue
            existing_id = state.find_entity_id(entity_id) or state.find_entity_id(str(entity.get("name") or ""))
            if existing_id:
                return existing_id

            entity["_origin_kind"] = "derived"
            entity["_source_action"] = action_family(action)
            entity["_source_entity_id"] = source_id
            entity["_rule_id"] = f"implied:{_implied_kind(implied)}"
            state.apply_changes({"spawn_entities": {entity_id: entity}})
            return entity_id
    return ""


def _iter_implied_specs(source: dict[str, Any], target_text: str, state: Any) -> list[Any]:
    specs: list[Any] = []
    for key in ("implied_equipment", "implied_entities"):
        value = source.get(key, [])
        if isinstance(value, str):
            specs.append(value)
        elif isinstance(value, list):
            specs.extend(value)
    specs.extend(_rule_implied_specs(source, target_text, state))
    return specs


def _rule_implied_specs(source: dict[str, Any], target_text: str, state: Any) -> list[Any]:
    specs: list[Any] = []
    rules = []
    configured_rules = state.script.get("implied_entity_rules", [])
    if isinstance(configured_rules, list):
        rules.extend(configured_rules)

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when", {})
        if not isinstance(when, dict):
            continue
        if not _matches_source_terms(source, when.get("source_terms", [])):
            continue
        target_terms = when.get("target_terms", [])
        if target_terms and not _matches_target_terms(target_text, target_terms, source):
            continue
        implies = rule.get("implies", [])
        if isinstance(implies, str):
            specs.append(implies)
        elif isinstance(implies, list):
            specs.extend(implies)
    return specs


def _resolve_implied_template(implied: Any, state: Any) -> dict[str, Any]:
    if isinstance(implied, dict) and "entity" in implied:
        return deepcopy(implied)

    kind = _canonical_implied_kind(_implied_kind(implied))
    templates = state.script.get("implied_entity_templates", {})
    if isinstance(templates, dict) and isinstance(templates.get(kind), dict):
        return deepcopy(templates[kind])
    return {}


def _render_implied_entity(
    template: dict[str, Any],
    source_id: str,
    source: dict[str, Any],
    state: Any,
) -> dict[str, Any]:
    entity = template.get("entity", {})
    if not isinstance(entity, dict):
        entity = {}
    return _render_source_value(entity, source_id, source, state)


def _matches_implied_target(target_text: str, entity: dict[str, Any], implied: Any, source: dict[str, Any]) -> bool:
    candidates = _target_candidates(target_text, source)
    names = [
        _canonical_implied_kind(_implied_kind(implied)),
        _implied_kind(implied),
        str(entity.get("name") or ""),
        *[str(alias) for alias in entity.get("aliases", [])],
        *[str(tag) for tag in entity.get("tags", [])],
    ]
    normalized_names = {name.lower().strip() for name in names if name}
    return any(
        candidate and name and (candidate in name or name in candidate)
        for candidate in candidates
        for name in normalized_names
    )


def _implied_kind(implied: Any) -> str:
    if isinstance(implied, str):
        return implied
    if isinstance(implied, dict):
        return str(implied.get("kind") or implied.get("id") or implied.get("name") or "")
    return ""


def _canonical_implied_kind(kind: str) -> str:
    return kind


def _target_candidates(target_text: str, source: dict[str, Any]) -> set[str]:
    normalized = target_text.lower().strip()
    candidates = {normalized, _strip_possessive(normalized, source)}
    return {candidate for candidate in candidates if candidate}


def _strip_possessive(text: str, source: dict[str, Any]) -> str:
    stripped = text.strip()
    for prefix in PRONOUN_POSSESSIVES:
        if stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip()
    source_names = [
        str(source.get("name") or ""),
        *[str(alias) for alias in source.get("aliases", [])],
    ]
    for source_name in sorted(set(source_names), key=len, reverse=True):
        prefix = f"{source_name.lower()}的"
        if source_name and stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip()
    if "的" in stripped:
        return stripped.split("的", 1)[1].strip()
    return stripped


def _matches_source_terms(source: dict[str, Any], source_terms: object) -> bool:
    if isinstance(source_terms, str):
        source_terms = [source_terms]
    if not isinstance(source_terms, list):
        return False
    source_values = [
        str(source.get("name") or ""),
        *[str(alias) for alias in source.get("aliases", [])],
        *[str(tag) for tag in source.get("tags", [])],
        str(source.get("type") or ""),
    ]
    normalized_values = [value.lower() for value in source_values if value]
    return any(
        term and any(term.lower() in value or value in term.lower() for value in normalized_values)
        for term in source_terms
    )


def _matches_target_terms(target_text: str, target_terms: object, source: dict[str, Any]) -> bool:
    if isinstance(target_terms, str):
        target_terms = [target_terms]
    if not isinstance(target_terms, list):
        return False
    candidates = _target_candidates(target_text, source)
    return any(
        term and any(term.lower() in candidate or candidate in term.lower() for candidate in candidates)
        for term in target_terms
    )


def _render_source_value(value: Any, source_id: str, source: dict[str, Any], state: Any) -> Any:
    def _leaf(v: Any) -> Any:
        return _render_source_template(v, source_id, source, state) if isinstance(v, str) else v
    return traverse_replace(value, _leaf)


def _render_source_template(value: str, source_id: str, source: dict[str, Any], state: Any) -> str:
    return (
        value.replace("$source_id", source_id)
        .replace("$source_name", str(source.get("name") or source_id))
        .replace("$turn_id", str(getattr(state, "turn_id", 0)))
    )
