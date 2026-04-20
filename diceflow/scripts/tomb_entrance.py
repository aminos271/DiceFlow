from __future__ import annotations


SCRIPT = {
    "id": "tomb_entrance",
    "title": "古墓入口",
    "intro": "DiceFlow MVP：20 轮内逃出古墓。输入 q/quit/退出 结束。",
    "invalid_action_event": "行动没有成立，但局势没有停下，守卫继续压迫你的空间。",
    "player": {
        "hp": 10,
        "max_hp": 10,
        "inventory": ["短剑", "火把"],
        "location": "古墓入口",
    },
    "scene": {
        "name": "古墓入口",
        "description": "昏暗石室里潮气很重。一个守卫挡在左门前，门缝里透出微弱冷光。",
    },
    "flags": {
        "found_exit": False,
        "door_open": False,
        "game_over": False,
        "ending": "",
    },
    "entities": {
        "guard_1": {
            "name": "守卫",
            "aliases": ["守卫", "卫兵", "敌人", "看守"],
            "metadata": {
                "allowed_actions": ["attack", "talk", "inspect"],
                "actions": {
                    "attack": {
                        "dc": 12,
                        "outcomes": {
                            "critical_success": {
                                "entities": {"$target": {"hp_delta": -5}},
                                "events": ["你抓住破绽重创守卫。"],
                            },
                            "success": {
                                "entities": {"$target": {"hp_delta": -3}},
                                "events": ["你的攻击命中守卫。"],
                            },
                            "fail": {
                                "player": {"hp_delta": -1},
                                "events": ["守卫挡下攻击，但他的站位暴露了左门锁孔。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -2},
                                "events": ["攻击落空，守卫反击得手。"],
                            },
                        },
                    },
                    "talk": {
                        "dc": 13,
                        "outcomes": {
                            "critical_success": {
                                "entities": {"$target": {"hostile": False}},
                                "events": ["守卫的敌意明显动摇，攻击他的难度降低了。"],
                            },
                            "success": {
                                "entities": {"$target": {"hostile": False}},
                                "events": ["守卫的敌意短暂动摇，攻击他的难度降低了。"],
                            },
                            "fail": {
                                "player": {"hp_delta": -1},
                                "events": ["交涉失败，守卫用盾牌把你逼退。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -2},
                                "events": ["你的话激怒了守卫，他立刻逼近反击。"],
                            },
                        },
                    },
                    "inspect": {
                        "dc": 10,
                        "outcomes": {
                            "critical_success": {
                                "events": ["你看穿守卫换手时的破绽，下一次进攻会更容易。"],
                            },
                            "success": {
                                "events": ["你观察到守卫每次换手都会露出短暂破绽。"],
                            },
                            "fail": {
                                "events": ["你没看出更多信息，但守卫仍被牵制在左门前。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -1},
                                "events": ["你检查时分神，守卫逼近并让你撞上石壁。"],
                            },
                        },
                    },
                },
            },
            "hp": 6,
            "max_hp": 6,
            "alive": True,
            "location": "入口",
            "hostile": True,
        },
        "left_door": {
            "name": "左门",
            "aliases": ["左门", "门", "石门", "出口"],
            "metadata": {
                "allowed_actions": ["open", "use", "inspect"],
                "actions": {
                    "open": {
                        "dc": 14,
                        "outcomes": {
                            "critical_success": {
                                "entities": {"$target": {"locked": False}},
                                "flags": {"found_exit": True, "door_open": True},
                                "events": ["左门猛地打开，冷光后的通道显露出来。"],
                            },
                            "success": {
                                "entities": {"$target": {"locked": False}},
                                "flags": {"found_exit": True, "door_open": True},
                                "events": ["左门打开，冷光后的通道显露出来。"],
                            },
                            "fail": {
                                "entities": {"$target": {"weakened": True}},
                                "flags": {"found_exit": True},
                                "events": ["门没有打开，但锁芯松动，你确认门后就是出口。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -2},
                                "entities": {"$target": {"weakened": True}},
                                "events": ["门锁崩裂弹片划伤你，但锁芯已经松动。"],
                            },
                        },
                    },
                    "use": {
                        "dc": 10,
                        "required_tools": ["火把"],
                        "outcomes": {
                            "critical_success": {
                                "entities": {"$target": {"weakened": True}},
                                "flags": {"found_exit": True},
                                "events": ["火把精准烤裂门锁外壳，锁芯变得很脆弱。"],
                            },
                            "success": {
                                "entities": {"$target": {"weakened": True}},
                                "flags": {"found_exit": True},
                                "events": ["火把烤裂了门锁外壳，锁芯更容易处理了。"],
                            },
                            "fail": {
                                "entities": {"$target": {"weakened": True}},
                                "events": ["火焰没烧开门，却照出了锁孔旁的裂缝。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -1, "inventory_remove": ["火把"]},
                                "events": ["火把爆出火星灼伤你的手，火把也熄灭了。"],
                            },
                        },
                    },
                    "inspect": {
                        "dc": 10,
                        "outcomes": {
                            "critical_success": {
                                "flags": {"found_exit": True},
                                "entities": {"$target": {"weakened": True}},
                                "events": ["你看清左门锁孔磨损严重，门后有风声。"],
                            },
                            "success": {
                                "flags": {"found_exit": True},
                                "entities": {"$target": {"weakened": True}},
                                "events": ["你看清左门锁孔磨损严重，门后有风声。"],
                            },
                            "fail": {
                                "flags": {"found_exit": True},
                                "events": ["你没找到机关，但确认左门后有可通行的空间。"],
                            },
                            "critical_fail": {
                                "player": {"hp_delta": -1},
                                "events": ["你检查时分神，守卫逼近并让你撞上石壁。"],
                            },
                        },
                    },
                },
            },
            "type": "door",
            "locked": True,
            "burnable": True,
            "weakened": False,
        },
    },
    "scene_actions": {
        "flee": {
            "dc": 12,
            "outcomes": {
                "critical_success": {
                    "flags": {"found_exit": True},
                    "events": ["你拉开距离，找到通往左门的短暂空隙。"],
                },
                "success": {
                    "flags": {"found_exit": True},
                    "events": ["你拉开距离，找到通往左门的短暂空隙。"],
                },
                "fail": {
                    "player": {"hp_delta": -1},
                    "events": ["你没能脱离守卫的控制范围。"],
                },
                "critical_fail": {
                    "player": {"hp_delta": -2},
                    "events": ["你后退时踩空，守卫趁机追击。"],
                },
            },
        },
        "wait": {
            "dc": 8,
            "outcomes": {
                "critical_success": {
                    "events": ["你稳住呼吸，完整看清了守卫的攻击节奏。"],
                },
                "success": {
                    "events": ["你稳住呼吸，观察到守卫每次换手都会露出破绽。"],
                },
                "fail": {
                    "player": {"hp_delta": -1},
                    "events": ["你停得太久，守卫向前压迫并迫使你后退。"],
                },
                "critical_fail": {
                    "player": {"hp_delta": -2},
                    "events": ["你停得太久，守卫直接冲了上来。"],
                },
            },
        },
        "unknown": {
            "dc": 12,
            "outcomes": {
                "critical_success": {
                    "events": ["你短暂迟疑后仍稳住了局势，找到一个新的观察角度。"],
                },
                "success": {
                    "events": ["你短暂迟疑，但仍让局势向前推进。"],
                },
                "fail": {
                    "player": {"hp_delta": -1},
                    "events": ["迟疑让守卫抢占了位置，你被逼退并擦伤。"],
                },
                "critical_fail": {
                    "player": {"hp_delta": -2},
                    "events": ["迟疑让守卫完全抢占先机，你被重重逼退。"],
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
                "flags": {"door_open": True},
                "entities": {"guard_1": {"alive": False}},
            },
        },
        {
            "ending": "timeout",
            "when": {"turn_id_gte": 20},
        },
    ],
}
