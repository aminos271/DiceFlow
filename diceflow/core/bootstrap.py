from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

# ── Generic action specs for core families ────────────────────────────

GENERIC_ACTION_SPECS: dict[str, dict[str, Any]] = {
    "attack": {
        "dc": 12,
        "outcomes": {
            "critical_success": {
                "entities": {"$target": {"hp_delta": -5, "hostile": True}},
                "events": ["你精准地击中了目标，造成严重伤害。"],
            },
            "success": {
                "entities": {"$target": {"hp_delta": -3, "hostile": True}},
                "events": ["你的攻击命中目标。"],
            },
            "fail": {
                "events": ["你的攻击落空了。"],
            },
            "critical_fail": {
                "player": {"hp_delta": -1},
                "entities": {"$target": {"hostile": True}},
                "events": ["攻击失误让你露出破绽，受到轻微反击。"],
            },
        },
    },
    "talk": {
        "dc": 10,
        "outcomes": {
            "critical_success": {
                "entities": {"$target": {"favorability_delta": 2, "hostile": False}},
                "events": ["对方对你的态度明显改善。"],
            },
            "success": {
                "entities": {"$target": {"favorability_delta": 1}},
                "events": ["对方愿意继续听你说。"],
            },
            "fail": {
                "events": ["对方对你的话反应冷淡。"],
            },
            "critical_fail": {
                "entities": {"$target": {"favorability_delta": -2, "hostile": True}},
                "events": ["你的话语激怒了对方。"],
            },
        },
    },
    "inspect": {
        "dc": 10,
        "outcomes": {
            "critical_success": {
                "events": ["你仔细观察，发现了隐藏的细节和潜在线索。"],
            },
            "success": {
                "events": ["你观察了周围的情况，确认了一些有用的信息。"],
            },
            "fail": {
                "events": ["你没有发现什么特别的东西。"],
            },
            "critical_fail": {
                "events": ["你被环境干扰，完全错过了重要的线索。"],
            },
        },
    },
    "take": {
        "dc": 10,
        "outcomes": {
            "critical_success": {
                "move_item_to_inventory": ["$target"],
                "events": ["你迅速将$target_name拿到手中。"],
            },
            "success": {
                "move_item_to_inventory": ["$target"],
                "events": ["你拿起了$target_name。"],
            },
            "fail": {
                "events": ["$target_name暂时无法拿到，你需要再试一次。"],
            },
            "critical_fail": {
                "events": ["你在尝试拿$target_name时手滑了，物品掉落到更难够到的位置。"],
            },
        },
    },
    "open": {
        "dc": 12,
        "outcomes": {
            "critical_success": {
                "entities": {"$target": {"opened": True, "locked": False}},
                "events": ["$target_name被顺利打开了。"],
            },
            "success": {
                "entities": {"$target": {"opened": True, "locked": False}},
                "events": ["$target_name被打开了。"],
            },
            "fail": {
                "events": ["$target_name卡住了，你需要再试一次。"],
            },
            "critical_fail": {
                "player": {"hp_delta": -1},
                "events": ["用力过猛，$target_name反震让你擦伤了。"],
            },
        },
    },
    "use": {
        "dc": 12,
        "outcomes": {
            "critical_success": {
                "events": ["你熟练地使用了$tool_name，效果出奇地好。"],
            },
            "success": {
                "events": ["你使用了$tool_name。"],
            },
            "fail": {
                "events": ["$tool_name没有产生预期的效果。"],
            },
            "critical_fail": {
                "player": {"hp_delta": -1},
                "events": ["$tool_name的使用出现了意外，反作用力让你受了轻伤。"],
            },
        },
    },
    "flee": {
        "dc": 10,
        "outcomes": {
            "critical_success": {
                "events": ["你抓住时机迅速脱离了危险区域。"],
            },
            "success": {
                "events": ["你成功拉开了距离。"],
            },
            "fail": {
                "events": ["撤退受阻，你暂时无法脱离当前局势。"],
            },
            "critical_fail": {
                "player": {"hp_delta": -1},
                "events": ["撤退失败，你在慌乱中受到了一些伤害。"],
            },
        },
    },
    "wait": {
        "dc": 5,
        "outcomes": {
            "critical_success": {
                "events": ["你耐心等待，同时敏锐地观察到了局势的微妙变化。"],
            },
            "success": {
                "events": ["你屏息等待，局势仍在推进。"],
            },
            "fail": {
                "events": ["等待并没有带来新的变化。"],
            },
            "critical_fail": {
                "events": ["在你等待时，局势变得对你不利。"],
            },
        },
    },
}

GENERIC_DEFAULT_ENTITY_ACTIONS: dict[str, list[str]] = {
    "npc": ["attack", "talk", "inspect"],
    "item": ["take", "inspect", "use"],
    "pickup": ["take", "inspect"],
    "container": ["open", "inspect"],
    "door": ["open", "inspect"],
    "obstacle": ["inspect"],
    "clue": ["inspect"],
}

# ── WorldBootstrap ────────────────────────────────────────────────────


@dataclass
class WorldBootstrap:
    """Structured data to initialize a GameState without a YAML script."""
    world_id: str
    title: str
    intro: str = ""
    player: dict = field(default_factory=lambda: {"hp": 10, "max_hp": 10, "inventory": [], "location": ""})
    scene: dict = field(default_factory=lambda: {"name": "未知场景", "description": ""})
    entities: dict[str, dict] = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    ending_conditions: list[dict] = field(default_factory=lambda: [
        {"when": {"turn_id_gte": 20}, "ending": "timeout"},
        {"when": {"player_hp_lte": 0}, "ending": "death"},
    ])
    world: dict | None = None
    scene_actions: dict = field(default_factory=dict)
    dynamic_entity_templates: dict = field(default_factory=dict)
    generic_rules: list[dict] = field(default_factory=list)
    action_rules: list[dict] = field(default_factory=list)
    dc_modifiers: list[dict] = field(default_factory=list)
    derivation_rules: list[dict] = field(default_factory=list)
    reaction_rules: list[dict] = field(default_factory=list)
    runtime_generation_hooks: list[dict] = field(default_factory=list)
    invalid_action_event: str = "行动没有成立，但局势仍在推进。"
    default_no_outcome_event: str = "局势发生了变化，你必须立刻决定下一步。"
    ending_texts: dict = field(default_factory=dict)
    locations: dict = field(default_factory=dict)
    world_model: dict = field(default_factory=dict)
    world_clock: dict = field(default_factory=dict)

    def to_script_dict(self) -> dict[str, Any]:
        """Produce a dict that satisfies the minimal Script interface."""
        return {
            "id": self.world_id,
            "schema_version": 1,
            "title": self.title,
            "world_id": self.world_id,
            "intro": self.intro,
            "player": deepcopy(self.player),
            "scene": deepcopy(self.scene),
            "entities": deepcopy(self.entities),
            "flags": deepcopy(self.flags),
            "ending_conditions": deepcopy(self.ending_conditions),
            "world": deepcopy(self.world) if self.world else None,
            "scene_actions": deepcopy(self.scene_actions),
            "dynamic_entity_templates": deepcopy(self.dynamic_entity_templates),
            "generic_rules": deepcopy(self.generic_rules),
            "action_rules": deepcopy(self.action_rules),
            "dc_modifiers": deepcopy(self.dc_modifiers),
            "derivation_rules": deepcopy(self.derivation_rules),
            "reaction_rules": deepcopy(self.reaction_rules),
            "runtime_generation_hooks": deepcopy(self.runtime_generation_hooks),
            "invalid_action_event": self.invalid_action_event,
            "default_no_outcome_event": self.default_no_outcome_event,
            "ending_texts": deepcopy(self.ending_texts),
            "locations": deepcopy(self.locations),
            "world_model": deepcopy(self.world_model),
            "world_clock": deepcopy(self.world_clock),
        }


# ── Factory functions ─────────────────────────────────────────────────


def bootstrap_from_lorebook(lorebook: Any, world_id: str | None = None) -> WorldBootstrap | None:
    """Create a WorldBootstrap from a SessionLore instance.

    Reads lorebook entries and optional world content to construct
    a fully-specified bootstrap. Returns None if there is not enough
    data to construct a minimal bootstrap.
    """
    # Try to load world content first for richer bootstrap
    world_content: dict[str, Any] | None = None
    effective_world_id = world_id

    if effective_world_id:
        try:
            from diceflow.content.worlds.loader import load_world_content, world_exists
            if world_exists(effective_world_id):
                world_content = load_world_content(effective_world_id)
        except Exception:
            world_content = None

    # ── Extract from lorebook ────────────────────────────────────
    entries_by_type = _extract_lorebook_entries(lorebook)

    if world_content:
        detailed_bootstrap = _bootstrap_from_world_config(world_content, effective_world_id)
        if detailed_bootstrap is not None:
            return detailed_bootstrap

    # ── Build title and intro ─────────────────────────────────────
    title = ""
    intro = ""

    if world_content:
        meta = world_content.get("meta", {})
        title = str(meta.get("title") or effective_world_id or "")
        intro = str(meta.get("description") or "")
    else:
        # From lorebook world entries
        world_entries = entries_by_type.get("world_entries", [])
        if world_entries:
            title = str(world_entries[0].get("title", "未知世界"))
            intro = str(world_entries[0].get("summary", ""))
        else:
            # Need at least some world data
            title = effective_world_id or "未知世界"

    # ── Build scene from first location entry ────────────────────
    scene: dict[str, Any] = {"name": "起点", "description": ""}

    if world_content:
        locations = world_content.get("locations", [])
        if locations:
            loc = locations[0]
            scene = {
                "name": str(loc.get("title") or loc.get("id", "未知地点")),
                "description": str(loc.get("content") or loc.get("summary", "")),
            }
    else:
        location_entries = entries_by_type.get("location_entries", [])
        if location_entries:
            loc = location_entries[0]
            scene = {
                "name": str(loc.get("title", "未知地点")),
                "description": str(loc.get("content") or loc.get("summary", "")),
            }

    # ── Build entities from character entries ────────────────────
    entities: dict[str, dict[str, Any]] = {}
    entity_index = 0

    if world_content:
        for char in world_content.get("characters", []):
            entity_index += 1
            eid = str(char.get("linked_entity_id") or f"char_{entity_index}")
            entities[eid] = _character_to_entity(char, eid)
    else:
        for char in entries_by_type.get("character_entries", []):
            entity_index += 1
            eid = str(char.get("linked_entity_id") or f"char_{entity_index}")
            entities[eid] = _character_to_entity(char, eid)

    if not entities:
        # Ensure at least one entity exists for a minimal game
        entities["npc_1"] = {
            "type": "npc",
            "name": "陌生人",
            "tags": ["npc"],
            "disposition": "neutral",
            "personality": {"traits": ["沉默寡言"], "manner": "低声说话", "motivation": "观察来客"},
        }

    # ── Build world contract ──────────────────────────────────────
    world_contract: dict[str, Any] | None = None
    if world_content:
        meta = world_content.get("meta", {})
        world_contract = {
            "premise": str(meta.get("description") or title),
            "tone": "",
            "allowed_scene_types": ["corridor", "chamber", "tavern", "wilderness"],
            "allowed_entity_types": ["npc", "item", "pickup", "container", "door", "obstacle", "clue"],
            "forbidden": [],
            "max_runtime_dc": 14,
            "max_new_entities_per_transition": 3,
        }

    # ── Assemble bootstrap ────────────────────────────────────────
    bootstrap = WorldBootstrap(
        world_id=effective_world_id or "",
        title=title,
        intro=intro or f"欢迎来到{title}。",
        player={"hp": 10, "max_hp": 10, "inventory": [], "location": str(scene.get("name", ""))},
        scene=scene,
        entities=entities,
        flags={},
        ending_conditions=[
            {"when": {"turn_id_gte": 20}, "ending": "timeout"},
            {"when": {"player_hp_lte": 0}, "ending": "death"},
        ],
        world=world_contract,
        scene_actions={},
        dynamic_entity_templates={},
    )
    return bootstrap


def bootstrap_from_defaults(world_id: str | None = None) -> WorldBootstrap:
    """Create a minimal default bootstrap without requiring lorebook or scripts.

    Produces a generic tavern scene with one innkeeper NPC.
    """
    world_id = world_id or "_default"
    return WorldBootstrap(
        world_id=world_id,
        title="边境旅店",
        intro="你推开旅店沉重的橡木门，温暖的炉火气息扑面而来。大厅里稀稀落落坐着几个客人，吧台后面站着一个正在擦拭杯子的男人。",
        player={"hp": 10, "max_hp": 10, "inventory": [], "location": "边境旅店"},
        scene={
            "name": "边境旅店大厅",
            "description": "旅店大厅里炉火正旺，几张木桌散落在大厅各处。吧台后的架子上摆满了各式酒瓶，空气中弥漫着麦酒和烤肉的香气。角落里坐着一个披斗篷的旅人，门外的冷风偶尔从门缝中钻进来。",
        },
        entities={
            "innkeeper": {
                "type": "npc",
                "name": "旅店老板",
                "aliases": ["老板", "掌柜", "店主"],
                "tags": ["npc"],
                "disposition": "friendly",
                "personality": {
                    "traits": ["热情", "健谈", "消息灵通"],
                    "manner": "笑容满面",
                    "motivation": "经营旅店，希望客人满意",
                },
            },
        },
        flags={},
        ending_conditions=[
            {"when": {"turn_id_gte": 20}, "ending": "timeout"},
            {"when": {"player_hp_lte": 0}, "ending": "death"},
        ],
        world={
            "premise": "边境旅店是冒险者们旅途中的歇脚之处，各路消息在此交汇。",
            "tone": "温暖、热闹、市井",
            "allowed_scene_types": ["tavern", "corridor", "chamber", "wilderness", "market"],
            "allowed_entity_types": ["npc", "item", "pickup", "container", "door", "obstacle", "clue"],
            "forbidden": [],
            "max_runtime_dc": 14,
            "max_new_entities_per_transition": 3,
        },
        scene_actions={},
        dynamic_entity_templates={},
    )


# ── Helpers ───────────────────────────────────────────────────────────


def _extract_lorebook_entries(lorebook: Any) -> dict[str, list[dict[str, Any]]]:
    """Extract entries from a SessionLore instance grouped by type."""
    result: dict[str, list[dict[str, Any]]] = {
        "world_entries": [],
        "location_entries": [],
        "character_entries": [],
        "event_entries": [],
    }
    if lorebook is None:
        return result
    try:
        for entry in lorebook.all_entries():
            entry_type = str(getattr(entry, "type", ""))
            entry_dict = entry.to_dict() if hasattr(entry, "to_dict") else {}
            if entry_type == "world":
                result["world_entries"].append(entry_dict)
            elif entry_type == "location":
                result["location_entries"].append(entry_dict)
            elif entry_type == "character":
                result["character_entries"].append(entry_dict)
            elif entry_type == "event":
                result["event_entries"].append(entry_dict)
    except Exception:
        pass
    return result


def _bootstrap_from_world_config(
    world_content: dict[str, Any],
    world_id: str | None,
) -> WorldBootstrap | None:
    config = world_content.get("bootstrap")
    if not isinstance(config, dict):
        return None

    meta = world_content.get("meta", {})
    effective_world_id = str(world_id or meta.get("id") or config.get("world_id") or config.get("id") or "")
    title = str(config.get("title") or meta.get("title") or effective_world_id or "未知世界")
    intro = str(config.get("intro") or meta.get("description") or "")

    return WorldBootstrap(
        world_id=effective_world_id,
        title=title,
        intro=intro,
        player=deepcopy(config.get("player", {})),
        scene=deepcopy(config.get("scene", {})),
        entities=deepcopy(config.get("entities", {})),
        flags=deepcopy(config.get("flags", {})),
        ending_conditions=deepcopy(config.get("ending_conditions", [])),
        world=deepcopy(config.get("world")),
        scene_actions=deepcopy(config.get("scene_actions", {})),
        dynamic_entity_templates=deepcopy(config.get("dynamic_entity_templates", {})),
        generic_rules=deepcopy(config.get("generic_rules", [])),
        action_rules=deepcopy(config.get("action_rules", [])),
        dc_modifiers=deepcopy(config.get("dc_modifiers", [])),
        derivation_rules=deepcopy(config.get("derivation_rules", [])),
        reaction_rules=deepcopy(config.get("reaction_rules", [])),
        runtime_generation_hooks=deepcopy(config.get("runtime_generation_hooks", [])),
        invalid_action_event=str(config.get("invalid_action_event", "行动没有成立，但局势仍在推进。")),
        default_no_outcome_event=str(config.get("default_no_outcome_event", "局势发生了变化，你必须立刻决定下一步。")),
        ending_texts=deepcopy(config.get("ending_texts", {})),
        locations=deepcopy(config.get("locations", {})),
        world_model=deepcopy(config.get("world_model", {})),
        world_clock=deepcopy(config.get("world_clock", {})),
    )


def _character_to_entity(char: dict[str, Any], default_id: str) -> dict[str, Any]:
    """Convert a lorebook/world character entry to a game entity dict."""
    name = str(char.get("title") or char.get("id", default_id))
    summary = str(char.get("summary", ""))
    tags = [str(t) for t in char.get("tags", [])]
    entity: dict[str, Any] = {
        "type": "npc",
        "name": name,
        "tags": ["npc"] + [t for t in tags if t not in ("npc", "character")],
        "disposition": "neutral",
        "personality": {
            "traits": [],
            "manner": "",
            "motivation": summary if summary else "",
        },
    }

    # Derive disposition from summary/text
    if "敌对" in summary:
        entity["disposition"] = "hostile"
        entity["hostile"] = True
    elif "友善" in summary or "友好" in summary:
        entity["disposition"] = "friendly"
    elif "怀疑" in summary or "警惕" in summary:
        entity["disposition"] = "suspicious"

    # Extract personality traits from summary
    traits_match = summary
    if "特质:" in traits_match:
        traits_part = traits_match.split("特质:", 1)[1].split("；")[0].split(";")[0]
        entity["personality"]["traits"] = [t.strip() for t in traits_part.split(",") if t.strip()]
    if "举止:" in traits_match:
        manner_part = traits_match.split("举止:", 1)[1].split("；")[0].split(";")[0]
        entity["personality"]["manner"] = manner_part.strip()

    return entity
