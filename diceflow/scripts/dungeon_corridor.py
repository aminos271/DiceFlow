from __future__ import annotations

SCRIPT = {
    "id": "dungeon_corridor",
    "title": "地牢走廊",
    "intro": "你被困在一条阴暗的地牢走廊中。找到钥匙并打开铁门逃离。20 回合内完成。",
    "invalid_action_event": "你的行动没有奏效，但危险正在逼近。",

    "player": {
        "hp": 10,
        "max_hp": 10,
        "inventory": [],
        "location": "走廊",
    },

    "scene": {
        "name": "地牢走廊",
        "description": "狭长的石质走廊尽头是一扇沉重的铁门。一只巡逻的骷髅缓慢徘徊。角落里有一个破旧的木箱。",
    },

    "flags": {
        "has_key": False,
        "door_open": False,
        "game_over": False,
        "ending": "",
    },

    "entities": {
        "skeleton_1": {
            "name": "骷髅守卫",
            "aliases": ["骷髅", "守卫", "敌人"],
            "metadata": {
                "allowed_actions": ["attack", "inspect"],
                "actions": {
                    "attack": {
                        "dc": 11,
                        "outcomes": {
                            "critical_success": {
                                "entities": {"$target": {"hp_delta": -6}},
                                "events": ["你精准击碎骷髅的核心，它瞬间散架。"],
                            },
                            "success": {
                                "entities": {"$target": {"hp_delta": -3}},
                                "events": ["你的攻击击中了骷髅。"],
                            },
                            "fail": {
                                "player": {"hp_delta": -1},
                                "events": ["骷髅挡住攻击并反击。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -2},
                                "events": ["你失去平衡，被骷髅重击。"],
                            },
                        },
                    },
                    "inspect": {
                        "dc": 10,
                        "outcomes": {
                            "success": {
                                "events": ["你发现骷髅行动缓慢，似乎反应迟钝。"],
                            },
                            "fail": {
                                "events": ["你没有发现有用信息。"],
                            },
                        },
                    },
                },
            },
            "hp": 5,
            "max_hp": 5,
            "alive": True,
            "location": "走廊",
        },

        "chest_1": {
            "name": "木箱",
            "aliases": ["箱子", "木箱"],
            "metadata": {
                "allowed_actions": ["open", "inspect"],
                "actions": {
                    "open": {
                        "dc": 10,
                        "outcomes": {
                            "critical_success": {
                                "player": {"inventory_add": ["铁钥匙"]},
                                "flags": {"has_key": True},
                                "events": ["你轻松打开木箱，找到一把铁钥匙。"],
                            },
                            "success": {
                                "player": {"inventory_add": ["铁钥匙"]},
                                "flags": {"has_key": True},
                                "events": ["你打开木箱，找到一把铁钥匙。"],
                            },
                            "fail": {
                                "events": ["木箱卡住了，但你觉得还能再试。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -1},
                                "events": ["木箱突然崩裂碎片划伤你。"],
                            },
                        },
                    },
                    "inspect": {
                        "dc": 8,
                        "outcomes": {
                            "success": {
                                "events": ["你确认这个木箱可能藏有物品。"],
                            }
                        },
                    },
                },
            },
        },

        "iron_door": {
            "name": "铁门",
            "aliases": ["门", "铁门", "出口"],
            "metadata": {
                "allowed_actions": ["open", "inspect"],
                "actions": {
                    "open": {
                        "dc": 12,
                        "required_tools": ["铁钥匙"],
                        "outcomes": {
                            "critical_success": {
                                "flags": {"door_open": True},
                                "events": ["铁门被你顺利打开，出口就在眼前。"],
                            },
                            "success": {
                                "flags": {"door_open": True},
                                "events": ["铁门被打开，你看到了出口。"],
                            },
                            "fail": {
                                "events": ["钥匙卡住了，你需要再试一次。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -1},
                                "events": ["你用力过猛，钥匙滑脱划伤手指。"],
                            },
                        },
                    },
                    "inspect": {
                        "dc": 8,
                        "outcomes": {
                            "success": {
                                "events": ["这是一扇厚重铁门，需要钥匙才能打开。"],
                            }
                        },
                    },
                },
            },
            "locked": True,
        },
    },

    "scene_actions": {
        "move": {
            "dc": 9,
            "outcomes": {
                "critical_success": {
                    "events": ["你贴着墙根无声前进，靠近铁门时没有惊动骷髅。"],
                },
                "success": {
                    "events": ["你压低脚步向铁门移动，仍保持着与骷髅的距离。"],
                },
                "fail": {
                    "events": ["你靠近了铁门，但脚步声让骷髅转向你的方向。"],
                },
                "critical_fail": {
                    "player": {"hp_delta": -1},
                    "events": ["你踩到松动石块，骷髅立刻逼近并擦伤了你。"],
                },
            },
        },
        "flee": {
            "dc": 10,
            "outcomes": {
                "success": {
                    "events": ["你拉开距离，暂时避开了骷髅。"],
                },
                "fail": {
                    "player": {"hp_delta": -1},
                    "events": ["骷髅紧追不放。"],
                },
            },
        },
        "wait": {
            "dc": 8,
            "outcomes": {
                "success": {
                    "events": ["你稳定呼吸，观察局势。"],
                }
            },
        },
        "unknown": {
            "dc": 12,
            "outcomes": {
                "critical_success": {
                    "events": ["你短暂迟疑后重新掌握节奏，局势仍向前推进。"],
                },
                "success": {
                    "events": ["你调整姿态，谨慎地观察走廊中的威胁。"],
                },
                "fail": {
                    "player": {"hp_delta": -1},
                    "events": ["迟疑让骷髅靠近，你被迫后退并擦伤。"],
                },
                "critical_fail": {
                    "player": {"hp_delta": -2},
                    "events": ["你判断失误，骷髅抢先压上来重击了你。"],
                },
            },
        },
    },

    "ending_conditions": [
        {
            "ending": "death",
            "when": {"player_hp_lte": 0},
        },
        {
            "ending": "victory",
            "when": {
                "flags": {"door_open": True, "has_key": True},
            },
        },
        {
            "ending": "timeout",
            "when": {"turn_id_gte": 20},
        },
    ],
}

