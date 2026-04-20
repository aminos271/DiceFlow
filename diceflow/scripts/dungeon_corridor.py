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
                "allowed_actions": ["attack", "use", "inspect"],
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
                    "use": {
                        "dc": 10,
                        "required_tools": ["木箱"],
                        "outcomes": {
                            "critical_success": {
                                "entities": {"$target": {"hp_delta": -5}},
                                "set_entity_states": {
                                    "chest_1": {
                                        "destroyed": True,
                                        "available": False,
                                        "visible": False,
                                    }
                                },
                                "spawn_entities": {
                                    "chest_debris_1": {
                                        "name": "木箱残片",
                                        "aliases": ["残片", "碎片", "木箱残片"],
                                        "type": "debris",
                                        "contents": ["iron_key"],
                                        "metadata": {
                                            "allowed_actions": ["take", "inspect"],
                                            "actions": {
                                                "take": {
                                                    "dc": 6,
                                                    "outcomes": {
                                                        "success": {
                                                            "move_item_to_inventory": ["iron_key"],
                                                            "flags": {"has_key": True},
                                                            "set_entity_states": {"$target": {"looted": True}},
                                                            "events": ["你从木箱残片中翻出铁钥匙并收好。"],
                                                        },
                                                        "fail": {
                                                            "events": ["碎木片遮住了钥匙，你需要再翻找一次。"],
                                                        },
                                                    },
                                                },
                                                "inspect": {
                                                    "dc": 6,
                                                    "outcomes": {
                                                        "success": {
                                                            "events": ["残片之间露出一把铁钥匙。"],
                                                        }
                                                    },
                                                },
                                            },
                                        },
                                    }
                                },
                                "reveal_entities": ["iron_key"],
                                "events": ["你抡起木箱砸碎骷髅，箱体裂成残片，铁钥匙从里面露了出来。"],
                            },
                            "success": {
                                "entities": {"$target": {"hp_delta": -3}},
                                "set_entity_states": {
                                    "chest_1": {
                                        "destroyed": True,
                                        "available": False,
                                        "visible": False,
                                    }
                                },
                                "spawn_entities": {
                                    "chest_debris_1": {
                                        "name": "木箱残片",
                                        "aliases": ["残片", "碎片", "木箱残片"],
                                        "type": "debris",
                                        "contents": ["iron_key"],
                                        "metadata": {
                                            "allowed_actions": ["take", "inspect"],
                                            "actions": {
                                                "take": {
                                                    "dc": 6,
                                                    "outcomes": {
                                                        "success": {
                                                            "move_item_to_inventory": ["iron_key"],
                                                            "flags": {"has_key": True},
                                                            "set_entity_states": {"$target": {"looted": True}},
                                                            "events": ["你从木箱残片中翻出铁钥匙并收好。"],
                                                        },
                                                        "fail": {
                                                            "events": ["碎木片遮住了钥匙，你需要再翻找一次。"],
                                                        },
                                                    },
                                                },
                                                "inspect": {
                                                    "dc": 6,
                                                    "outcomes": {
                                                        "success": {
                                                            "events": ["残片之间露出一把铁钥匙。"],
                                                        }
                                                    },
                                                },
                                            },
                                        },
                                    }
                                },
                                "reveal_entities": ["iron_key"],
                                "events": ["木箱砸中骷髅后碎裂，残片散开，铁钥匙暴露出来。"],
                            },
                            "fail": {
                                "player": {"hp_delta": -1},
                                "events": ["你没能抡稳木箱，骷髅趁机逼近。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -2},
                                "events": ["木箱脱手撞在墙上，你被骷髅重击。"],
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
                                "entities": {"$target": {"opened": True}},
                                "reveal_entities": ["iron_key"],
                                "events": ["你轻松打开木箱，一把铁钥匙露了出来。"],
                            },
                            "success": {
                                "entities": {"$target": {"opened": True}},
                                "reveal_entities": ["iron_key"],
                                "events": ["你打开木箱，看见里面有一把铁钥匙。"],
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
            "contents": ["iron_key"],
        },

        "iron_key": {
            "name": "铁钥匙",
            "aliases": ["钥匙", "铁钥匙"],
            "type": "item",
            "item_id": "铁钥匙",
            "visible": False,
            "available": False,
            "metadata": {
                "allowed_actions": ["take", "inspect"],
                "actions": {
                    "take": {
                        "dc": 5,
                        "outcomes": {
                            "critical_success": {
                                "move_item_to_inventory": ["$target"],
                                "flags": {"has_key": True},
                                "events": ["你立刻捡起铁钥匙并收好。"],
                            },
                            "success": {
                                "move_item_to_inventory": ["$target"],
                                "flags": {"has_key": True},
                                "events": ["你拿起铁钥匙并收好。"],
                            },
                            "fail": {
                                "events": ["铁钥匙卡在木缝里，你需要再试一次。"],
                            },
                        },
                    },
                    "inspect": {
                        "dc": 5,
                        "outcomes": {
                            "success": {
                                "events": ["这是一把可以开启铁门的钥匙。"],
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
                "allowed_actions": ["open", "use", "inspect"],
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
                    "use": {
                        "dc": 12,
                        "required_tools": ["铁钥匙"],
                        "outcomes": {
                            "critical_success": {
                                "flags": {"door_open": True},
                                "events": ["你低调地把铁钥匙插入锁孔，铁门顺畅打开。"],
                            },
                            "success": {
                                "flags": {"door_open": True},
                                "events": ["铁钥匙转动锁芯，铁门被打开。"],
                            },
                            "fail": {
                                "events": ["钥匙卡住了，你需要调整角度再试一次。"],
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

