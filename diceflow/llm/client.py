from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from diceflow import config
from diceflow.core.dynamic_world import _world_contract
from diceflow.core.models import Action, CheckResult, StateChanges
from diceflow.core.state import GameState
from diceflow.llm.heuristics import (
    ACTION_KEYWORDS,
    USE_VERBS,
    _normalize_action,
    fallback_narration,
    heuristic_parse_intent,
)


PROMPT_DIR = Path(__file__).resolve().parent.parent / "content" / "prompts"
LLM_RETRY_ATTEMPTS = 2


class LLMClient:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_API_URL,
        )
        self.model = config.DEEPSEEK_MODEL_CHAT
        self.intent_prompt = (PROMPT_DIR / "intent_parser.txt").read_text(encoding="utf-8")
        self.narrator_prompt = (PROMPT_DIR / "narrator.txt").read_text(encoding="utf-8")
        self.dynamic_content_prompt = (PROMPT_DIR / "dynamic_content_generator.txt").read_text(encoding="utf-8")
        self.dynamic_world_prompt = (PROMPT_DIR / "dynamic_world_generator.txt").read_text(encoding="utf-8")
        self.open_ended_content_prompt = (PROMPT_DIR / "open_ended_content.txt").read_text(encoding="utf-8")
        self.npc_autonomy_prompt = (PROMPT_DIR / "npc_autonomy.txt").read_text(encoding="utf-8")

    def parse_intent(self, player_input: str, state: GameState) -> Action:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        content = self._chat(
            [
                {"role": "system", "content": self.intent_prompt},
                {
                    "role": "user",
                    "content": f"当前状态：{state_summary}\n玩家输入：{player_input}",
                },
            ],
            response_format={"type": "json_object"},
        )
        return _normalize_action(json.loads(content))

    def narrate(
        self,
        action: Action,
        check: CheckResult,
        changes: StateChanges,
        state: GameState,
    ) -> str:
        prompt = self.narrator_prompt.format(
            action=json.dumps(action, ensure_ascii=False),
            result=json.dumps(check, ensure_ascii=False),
            changes=json.dumps(changes, ensure_ascii=False),
            state=json.dumps(_compact_state(state), ensure_ascii=False),
        )
        return self._chat(
            [
                {"role": "system", "content": "你只输出叙事正文。"},
                {"role": "user", "content": prompt},
            ],
        ).strip()

    def evaluate_dynamic_action(self, action: Action, state: GameState) -> dict[str, Any]:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        action_summary = json.dumps(action, ensure_ascii=False)
        content = self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 TRPG 动态裁定助手，只做定性评估，不决定数值结果。"
                        "只输出 JSON：plausibility, difficulty, risk, intent_kind。"
                        "difficulty 只能是 easy、medium、hard、impossible。"
                        "如果合理，JSON 里可以加 spawn_entities 字段来描述生成的新实体（可生成 container / item / clue / obstacle / pickup / npc 类型）。"
                        "npc 类型限制：max_hp 不超过 5、只允许 inspect/talk/take 行动、不可设为 hostile 或 enemy。"
                        "pickup 类型限制：只是可拾取的小物品，不可为神器或通关关键物。"
                        "禁止让玩家直接通关、秒杀 Boss、无成本获得神器、修改主线设定或跳过核心挑战。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"当前状态：{state_summary}\n玩家行动：{action_summary}",
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    def generate_runtime_content(
        self,
        hook: dict[str, Any],
        action: Action,
        check: CheckResult,
        state: GameState,
    ) -> dict[str, Any]:
        content = self._chat(
            [
                {"role": "system", "content": self.dynamic_content_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "scene": state.scene,
                            "action": action,
                            "check": check,
                            "prompt_hint": hook.get("prompt_hint", ""),
                            "allowed_entity_types": hook.get("allowed_entity_types", []),
                            "max_dc": hook.get("max_dc", 15),
                            "existing_entity_ids": list(state.entities),
                            "state": _compact_state(state),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    def generate_dynamic_world(
        self,
        world: dict[str, Any],
        action: Action,
        validation: dict[str, Any],
        state: GameState,
    ) -> dict[str, Any]:
        content = self._chat(
            [
                {"role": "system", "content": self.dynamic_world_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "world": world,
                            "scene": state.scene,
                            "action": action,
                            "validation": validation,
                            "state": _compact_state(state),
                            "existing_scene_actions": list(state.script.get("scene_actions", {})),
                            "existing_entity_ids": list(state.entities),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    def generate_open_ended_content(
        self,
        action: Action,
        check: CheckResult,
        state: GameState,
        result_quality: str,
    ) -> dict[str, Any]:
        world = _world_contract(state)
        content = self._chat(
            [
                {"role": "system", "content": self.open_ended_content_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "world": world,
                            "scene": state.scene,
                            "action": action,
                            "check": check,
                            "result_quality": result_quality,
                            "state": _compact_state(state),
                            "allowed_entity_types": world["allowed_entity_types"],
                            "max_dc": world["max_runtime_dc"],
                            "existing_entity_ids": list(state.entities),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    def generate_npc_autonomy(
        self,
        visible_npcs: dict[str, Any],
        action: Action,
        state: GameState,
    ) -> dict[str, Any]:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        content = self._chat(
            [
                {"role": "system", "content": self.npc_autonomy_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "visible_npcs": visible_npcs,
                            "player_action": action,
                            "player_hp": state.player.get("hp", 0),
                            "scene": state.scene,
                            "recent_events": state.recent_events,
                            "turn_id": state.turn_id,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    def _chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            **kwargs,
        )
        return response.choices[0].message.content or ""


def parse_intent(player_input: str, state: GameState, llm: LLMClient | None = None) -> Action:
    if llm:
        for _ in range(LLM_RETRY_ATTEMPTS):
            try:
                return llm.parse_intent(player_input, state)
            except Exception:
                pass
    return heuristic_parse_intent(player_input, state)


def narrate(
    action: Action,
    check: CheckResult,
    changes: StateChanges,
    state: GameState,
    llm: LLMClient | None = None,
) -> str:
    if llm:
        for _ in range(LLM_RETRY_ATTEMPTS):
            try:
                text = llm.narrate(action, check, changes, state)
                if text:
                    return text
            except Exception:
                pass
    return fallback_narration(action, check, changes, state)



def _compact_state(state: GameState) -> dict[str, Any]:
    snapshot = state.get_snapshot()
    # Keys to strip from compact state to keep prompts lean
    _strip_keys = {"aliases", "max_hp", "equipped", "hooks", "metadata"}
    return {
        "player": snapshot["player"],
        "scene": {
            **snapshot["scene"],
            "visible_entities": [
                str(entity.get("name") or entity_id)
                for entity_id, entity in state.get_visible_entities().items()
            ],
        },
        "entities": {
            entity_id: {
                key: value
                for key, value in entity.items()
                if key not in _strip_keys
            }
            for entity_id, entity in state.get_visible_entities().items()
        },
        "flags": snapshot["flags"],
        "recent_events": snapshot["recent_events"],
    }


