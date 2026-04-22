from __future__ import annotations

from typing import Any

from diceflow.core.models import TurnRecord
from diceflow.core.state import GameState


SEPARATOR = "─" * 72


def render_status_panel(state: GameState) -> str:
    scene = state.get_current_scene()
    inventory = state.get_inventory_items()
    hostile_count = len(state.get_hostile_entities())
    return "\n".join(
        [
            render_separator(),
            f"回合 {state.turn_id + 1} | 场景：{scene.get('name', state.get_current_scene_id())}",
            f"HP：{state.player.get('hp', '?')}/{state.player.get('max_hp', '?')} | 背包：{_join_or_none(inventory)} | 威胁：{hostile_count}",
        ]
    )


def render_scene_panel(state: GameState) -> str:
    scene = state.get_current_scene()
    visible_entities = state.get_visible_entities()
    entity_labels = [_entity_label(entity_id, entity) for entity_id, entity in visible_entities.items()]
    return "\n".join(
        [
            "【周围】",
            str(scene.get("description") or "你还没有掌握这个场景的更多信息。"),
            f"可见实体：{_join_or_none(entity_labels)}",
        ]
    )


def render_action_hints(state: GameState) -> str:
    hints = state.get_available_action_hints()
    if not hints:
        hints = ["检查周围", "等待/观察局势"]
    return "【可尝试】" + "；".join(hints[:8])


def render_turn_result(record: TurnRecord) -> str:
    lines = [render_separator(), f"【判定】{record.summary}"]
    if record.check:
        lines.append(_render_check(record.check))
    else:
        lines.append(f"结果：无效行动 | 原因：{record.validation.get('reason', '未知')}")
    if record.narration:
        lines.extend(["【叙事】", record.narration])
    return "\n".join(lines)


def render_separator() -> str:
    return SEPARATOR


def render_debug(record: TurnRecord) -> str:
    return "\n".join(
        [
            "[debug]",
            f"action={record.action}",
            f"validation={record.validation}",
            f"check={record.check}",
            f"changes={record.state_changes}",
        ]
    )


def _render_check(check: dict[str, Any]) -> str:
    result = str(check.get("result", "unknown"))
    roll = check.get("roll", "?")
    dc = check.get("dc", "?")
    return f"骰子：d20={roll} / DC {dc} | 结果：{_result_label(result)}"


def _result_label(result: str) -> str:
    return {
        "critical_success": "大成功",
        "success": "成功",
        "fail": "失败",
        "critical_fail": "大失败",
    }.get(result, result)


def _entity_label(entity_id: str, entity: dict[str, Any]) -> str:
    name = str(entity.get("name") or entity_id)
    hp = entity.get("hp")
    max_hp = entity.get("max_hp")
    status: list[str] = []
    if hp is not None:
        status.append(f"HP {hp}/{max_hp or hp}")
    if entity.get("hostile") or "hostile" in entity.get("tags", []):
        status.append("敌对")
    if entity.get("locked"):
        status.append("上锁")
    if entity.get("opened"):
        status.append("已打开")
    if entity.get("destroyed"):
        status.append("损坏")
    return f"{name}（{'，'.join(status)}）" if status else name


def _join_or_none(items: list[str]) -> str:
    return "、".join(items) if items else "无"
