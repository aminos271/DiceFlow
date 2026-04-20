from __future__ import annotations

from diceflow.models import Action, CheckResult, StateChanges
from diceflow.state import GameState


def update_state(action: Action, check: CheckResult, state: GameState) -> StateChanges:
    action_type = str(action.get("type") or "unknown")
    result = str(check.get("result"))

    if action_type == "attack":
        return _attack_changes(action, result)
    if action_type == "open":
        return _open_changes(result, state)
    if action_type == "burn":
        return _burn_changes(result)
    if action_type == "inspect":
        return _inspect_changes(result)
    if action_type == "talk":
        return _talk_changes(result)
    if action_type == "flee":
        return _flee_changes(result)
    if action_type == "wait":
        return _wait_changes(result)

    return {
        "player": {"hp_delta": -1},
        "events": ["迟疑让守卫抢占了位置，你被逼退并擦伤。"],
    }


def _attack_changes(action: Action, result: str) -> StateChanges:
    target_id = action.get("target_id", "guard_1")
    if result == "critical_success":
        return {
            "entities": {target_id: {"hp_delta": -5}},
            "events": ["你抓住破绽重创守卫。"],
        }
    if result == "success":
        return {
            "entities": {target_id: {"hp_delta": -3}},
            "events": ["你的攻击命中守卫。"],
        }
    if result == "critical_fail":
        return {
            "player": {"hp_delta": -2},
            "events": ["攻击落空，守卫反击得手。"],
        }
    return {
        "player": {"hp_delta": -1},
        "events": ["守卫挡下攻击，但他的站位暴露了左门锁孔。"],
    }


def _open_changes(result: str, state: GameState) -> StateChanges:
    guard_alive = state.entities["guard_1"].get("alive", False)
    if guard_alive and result in {"success", "critical_success"}:
        return {
            "entities": {"left_door": {"locked": False}},
            "flags": {"found_exit": True},
            "player": {"hp_delta": -1},
            "events": ["你打开了锁，但守卫趁机划伤你，门还需要摆脱守卫后才能通过。"],
        }
    if result in {"success", "critical_success"}:
        return {
            "entities": {"left_door": {"locked": False}},
            "flags": {"found_exit": True, "door_open": True},
            "events": ["左门打开，冷光后的通道显露出来。"],
        }
    if result == "critical_fail":
        return {
            "player": {"hp_delta": -2},
            "entities": {"left_door": {"weakened": True}},
            "events": ["门锁崩裂弹片划伤你，但锁芯已经松动。"],
        }
    return {
        "entities": {"left_door": {"weakened": True}},
        "flags": {"found_exit": True},
        "events": ["门没有打开，但锁芯松动，你确认门后就是出口。"],
    }


def _burn_changes(result: str) -> StateChanges:
    if result in {"success", "critical_success"}:
        return {
            "entities": {"left_door": {"weakened": True}},
            "flags": {"found_exit": True},
            "events": ["火把烤裂了门锁外壳，锁芯更容易处理了。"],
        }
    if result == "critical_fail":
        return {
            "player": {"hp_delta": -1, "inventory_remove": ["火把"]},
            "events": ["火把爆出火星灼伤你的手，火把也熄灭了。"],
        }
    return {
        "entities": {"left_door": {"weakened": True}},
        "events": ["火焰没烧开门，却照出了锁孔旁的裂缝。"],
    }


def _inspect_changes(result: str) -> StateChanges:
    if result in {"success", "critical_success"}:
        return {
            "flags": {"found_exit": True},
            "entities": {"left_door": {"weakened": True}},
            "events": ["你看清左门锁孔磨损严重，门后有风声。"],
        }
    if result == "critical_fail":
        return {
            "player": {"hp_delta": -1},
            "events": ["你检查时分神，守卫逼近并让你撞上石壁。"],
        }
    return {
        "flags": {"found_exit": True},
        "events": ["你没找到机关，但确认左门后有可通行的空间。"],
    }


def _talk_changes(result: str) -> StateChanges:
    if result in {"success", "critical_success"}:
        return {
            "entities": {"guard_1": {"hostile": False}},
            "events": ["守卫的敌意短暂动摇，攻击他的难度降低了。"],
        }
    return {
        "player": {"hp_delta": -1},
        "events": ["交涉失败，守卫用盾牌把你逼退。"],
    }


def _flee_changes(result: str) -> StateChanges:
    if result in {"success", "critical_success"}:
        return {
            "flags": {"found_exit": True},
            "events": ["你拉开距离，找到通往左门的短暂空隙。"],
        }
    return {
        "player": {"hp_delta": -1},
        "events": ["你没能脱离守卫的控制范围。"],
    }


def _wait_changes(result: str) -> StateChanges:
    if result in {"success", "critical_success"}:
        return {"events": ["你稳住呼吸，观察到守卫每次换手都会露出破绽。"]}
    return {
        "player": {"hp_delta": -1},
        "events": ["你停得太久，守卫向前压迫并迫使你后退。"],
    }

