from __future__ import annotations

from typing import Any

from diceflow.core.models import TurnRecord
from diceflow.core.state import GameState
from diceflow.core.utils import result_label


# ── ANSI color codes ──────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
WHITE = "\033[97m"
GRAY = "\033[90m"

SEPARATOR_CHAR = "━"


# ── Public render functions ───────────────────────────────────────────

def render_separator(color: str = GRAY) -> str:
    return f"{color}{SEPARATOR_CHAR * 64}{RESET}"


def render_status_panel(state: GameState) -> str:
    scene = state.get_current_scene()
    inventory = state.get_inventory_items()
    hostile_count = len(state.get_hostile_entities())

    hp = state.player.get("hp", 0)
    max_hp = state.player.get("max_hp", 1)
    hp_color = _hp_color(hp, max_hp)
    threat_color = RED if hostile_count > 0 else GREEN

    return "\n".join(
        [
            "",
            render_separator(),
            f"  {CYAN}🎲 回合 {state.turn_id + 1}{RESET}  {YELLOW}📍 {scene.get('name', state.get_current_scene_id())}{RESET}",
            f"  {hp_color}❤️ {hp}/{max_hp}{RESET}  {WHITE}🎒 {_join_or_none(inventory)}{RESET}  {threat_color}⚔️ 威胁：{hostile_count}{RESET}",
        ]
    )


def render_scene_panel(state: GameState) -> str:
    scene = state.get_current_scene()
    visible = state.get_visible_entities()
    labels = [_entity_label(eid, e) for eid, e in visible.items()]
    return "\n".join(
        [
            f"  {GREEN}🌍 周围{RESET}",
            f"    {DIM}{scene.get('description', '')}{RESET}",
            f"  {BLUE}👀 可见实体：{_join_or_none(labels)}{RESET}",
        ]
    )


def render_action_hints(state: GameState) -> str:
    hints = state.get_available_action_hints()
    if not hints:
        hints = ["检查周围", "等待/观察局势"]
    hint_str = hints[0] + "".join(f"；{h}" for h in hints[1:8])
    return f"  {MAGENTA}💡 可尝试：{hint_str}{RESET}"


def render_turn_result(record: TurnRecord) -> str:
    lines: list[str] = []
    check = record.check
    if check:
        result = str(check.get("result", "unknown"))
        rc = _result_color(result)
        lines.append(f"\n  {rc}{_result_emoji(result)} {record.summary}{RESET}")
        lines.append(f"  {DIM}🎲 d20={check.get('roll', '?')} / DC {check.get('dc', '?')}  {rc}{result_label(result)}{RESET}")
    else:
        lines.append(f"\n  {RED}⛔ 无效行动 | {record.validation.get('reason', '未知')}{RESET}")
    if record.narration:
        lines.extend([f"  {DIM}📖 {record.narration}{RESET}"])
    return "\n".join(lines)


def render_debug(record: TurnRecord) -> str:
    return "\n".join(
        [
            f"{DIM}[debug]{RESET}",
            f"  {DIM}action={record.action}{RESET}",
            f"  {DIM}validation={record.validation}{RESET}",
            f"  {DIM}check={record.check}{RESET}",
            f"  {DIM}changes={record.state_changes}{RESET}",
        ]
    )


def render_prompt() -> str:
    return f"{CYAN}⚔ >>{RESET} "


def render_inventory_panel(state: GameState) -> str:
    items = state.get_inventory_items()
    if not items:
        return f"  {DIM}🎒 背包空空如也。{RESET}"
    label = "、".join(items)
    return f"  {WHITE}🎒 背包：{label}{RESET}"


def render_help_panel() -> str:
    lines = [
        f"  {CYAN}📖 DiceFlow 指令{RESET}",
        "",
        f"  {BOLD}回合动作（消耗回合）{RESET}",
        f"    直接输入你想做的事，例如：{GREEN}攻击守卫{RESET}、{GREEN}检查左门{RESET}、{GREEN}打开左门{RESET}",
        f"    用中文描述你的行动即可，系统会自动解析。",
        "",
        f"  {BOLD}查看指令（不消耗回合）{RESET}",
        f"    {GREEN}help / 帮助{RESET}        显示本帮助",
        f"    {GREEN}look / 看 / 观察{RESET}    重新查看周围环境",
        f"    {GREEN}inv / 背包{RESET}         查看背包中的物品",
        f"    {GREEN}status / 状态{RESET}      查看当前状态",
        f"    {GREEN}hint / 提示{RESET}        查看可尝试的行动",
        "",
        f"  {BOLD}系统指令{RESET}",
        f"    {GREEN}q / quit / 退出{RESET}    结束游戏",
    ]
    return "\n".join(lines)


def render_meta_result(text: str) -> str:
    return f"\n  {DIM}{text}{RESET}"


# ── Internal helpers ──────────────────────────────────────────────────

def _hp_color(hp: int, max_hp: int) -> str:
    ratio = hp / max(max_hp, 1)
    return RED if ratio <= 0.3 else (YELLOW if ratio <= 0.6 else GREEN)


def _result_color(result: str) -> str:
    return {
        "critical_success": GREEN,
        "success": GREEN,
        "fail": RED,
        "critical_fail": RED,
        "impossible": RED,
    }.get(result, WHITE)


def _result_emoji(result: str) -> str:
    return {
        "critical_success": "🌟",
        "success": "✅",
        "fail": "❌",
        "critical_fail": "💥",
        "impossible": "🚫",
    }.get(result, "❓")


def _entity_label(entity_id: str, entity: dict[str, Any]) -> str:
    name = str(entity.get("name") or entity_id)
    hp = entity.get("hp")
    max_hp = entity.get("max_hp")
    status: list[str] = []
    if hp is not None:
        status.append(f"❤️ {hp}/{max_hp or hp}")
    if entity.get("hostile") or "hostile" in entity.get("tags", []):
        status.append("🔴敌对")
    if entity.get("locked"):
        status.append("🔒上锁")
    if entity.get("opened"):
        status.append("🔓已打开")
    if entity.get("destroyed"):
        status.append("💔损坏")
    suffix = f"（{'，'.join(status)}）" if status else ""
    return f"{name}{suffix}"


def _join_or_none(items: list[str]) -> str:
    return "、".join(items) if items else "—"
