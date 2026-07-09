from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from openai import APIError, APIConnectionError, OpenAI

from diceflow import config
from diceflow.core.dynamic_world import _world_contract
from diceflow.core.models import Action, CheckResult, StateChanges, TurnResolution
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


def _build_intent_client() -> OpenAI:
    """Build client for intent parsing and dynamic adjudication.

    If INTENT_LLM_BASE_URL is set, use it (e.g. local Ollama).
    Otherwise fall back to DeepSeek defaults.
    """
    if config.INTENT_LLM_BASE_URL:
        return OpenAI(
            api_key=config.INTENT_LLM_API_KEY or "ollama",
            base_url=config.INTENT_LLM_BASE_URL,
        )
    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_API_URL,
    )


def _build_narration_client() -> OpenAI:
    """Build client for narration and content generation.

    If NARRATION_LLM_BASE_URL is set, use it.
    Otherwise fall back to DeepSeek defaults.
    """
    if config.NARRATION_LLM_BASE_URL:
        return OpenAI(
            api_key=config.NARRATION_LLM_API_KEY or "ollama",
            base_url=config.NARRATION_LLM_BASE_URL,
        )
    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_API_URL,
    )


def _intent_model() -> str:
    return config.INTENT_LLM_MODEL or config.DEEPSEEK_MODEL_CHAT


def _narration_model() -> str:
    return config.NARRATION_LLM_MODEL or config.DEEPSEEK_MODEL_CHAT


class LLMClient:
    def __init__(self) -> None:
        # Intent / adjudication client — required; failure is fatal
        self.intent_client = _build_intent_client()
        self.intent_model = _intent_model()

        # Narration / content client — optional; failure only disables narration
        self.narration_client: OpenAI | None = None
        self.narration_model: str = ""
        self._narration_available = False
        try:
            self.narration_client = _build_narration_client()
            self.narration_model = _narration_model()
            self._narration_available = True
        except Exception:
            logging.getLogger(__name__).warning(
                "Narration LLM client unavailable — narrator will use fallback",
                exc_info=True,
            )

        # Prompt templates
        self.intent_prompt = (PROMPT_DIR / "intent_parser.txt").read_text(encoding="utf-8")
        self.narrator_prompt = (PROMPT_DIR / "narrator.txt").read_text(encoding="utf-8")
        self.dynamic_content_prompt = (PROMPT_DIR / "dynamic_content_generator.txt").read_text(encoding="utf-8")
        self.dynamic_world_prompt = (PROMPT_DIR / "dynamic_world_generator.txt").read_text(encoding="utf-8")
        self.open_ended_content_prompt = (PROMPT_DIR / "open_ended_content.txt").read_text(encoding="utf-8")
        self.npc_autonomy_prompt = (PROMPT_DIR / "npc_autonomy.txt").read_text(encoding="utf-8")
        self.director_mode_prompt = (PROMPT_DIR / "director_mode.txt").read_text(encoding="utf-8")
        self.time_judge_prompt = (PROMPT_DIR / "time_judge.txt").read_text(encoding="utf-8")

    # ── Intent / Adjudication (use intent_client) ────────────────────

    def parse_intent(self, player_input: str, state: GameState) -> Action:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        content = self._intent_chat(
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

    def evaluate_dynamic_action(self, action: Action, state: GameState) -> dict[str, Any]:
        state_summary = json.dumps(_compact_state(state), ensure_ascii=False)
        action_summary = json.dumps(action, ensure_ascii=False)
        content = self._intent_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 TRPG 动态裁定助手，只做定性评估，不决定数值结果。"
                        "只输出 JSON：plausibility, difficulty, risk, intent_kind。"
                        "difficulty 只能是 easy、medium、hard、impossible。"
                        "不要输出 spawn_entities、events、state_changes 或任何生成内容。"
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

    def judge_time_impact(self, action: Action, state: GameState) -> dict[str, Any]:
        """Qualitatively judge how much in-world time an action consumes.

        Returns ``{"impact": "none|small|medium|large", "reason": ...}``.
        Only the bucket is LLM-produced; the segment advance is mapped by
        the time config's magnitude_table in the engine.
        """
        content = self._narration_chat(
            [
                {"role": "system", "content": self.time_judge_prompt},
                {"role": "user", "content": json.dumps(
                    {
                        "action": action,
                        "current_clock": state.world_clock,
                        "scene": state.scene,
                        "recent_events": state.recent_events,
                    },
                    ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    @property
    def narration_available(self) -> bool:
        return self._narration_available

    # ── Narration (uses narration_client) ────────────────────────────

    def narrate_turn(self, turn_resolution: TurnResolution) -> str:
        if not self._narration_available:
            raise RuntimeError("Narration LLM is not available")
        prompt = self.narrator_prompt.format(
            turn_resolution=json.dumps(turn_resolution, ensure_ascii=False),
        )
        return self._narration_chat(
            [
                {"role": "system", "content": "你只输出叙事正文。"},
                {"role": "user", "content": self._with_director_mode(prompt)},
            ],
        ).strip()

    # ── Unified content patch generator ──────────────────────────────

    def generate_content_patch(self, context: dict[str, Any]) -> dict[str, Any]:
        """Unified entry for LLM-driven content generation.

        ``context["mode"]`` determines which generator is called:

        - ``"open_ended"`` — roll-quality-dependent content after adjudication
        - ``"dynamic_world"`` — new scene/entities when player leaves scripted area
        - ``"runtime"`` — hook-driven content during standard resolution
        - ``"npc_autonomy"`` — NPC autonomous action generation

        All generated patches must pass their respective validators before
        being applied to game state.
        """
        mode = str(context.get("mode") or "")

        if mode == "open_ended":
            return self.generate_open_ended_content(
                action=context["action"],
                check=context["check"],
                state=context["state"],
                result_quality=context.get("quality", "unknown"),
            )
        elif mode == "dynamic_world":
            return self.generate_dynamic_world(
                world=context.get("world", _world_contract(context["state"])),
                action=context["action"],
                validation=context.get("validation", {}),
                state=context["state"],
            )
        elif mode == "runtime":
            return self.generate_runtime_content(
                hook=context["hook"],
                action=context["action"],
                check=context["check"],
                state=context["state"],
            )
        elif mode == "npc_autonomy":
            return self.generate_npc_autonomy(
                visible_npcs=context["visible_npcs"],
                action=context["action"],
                state=context["state"],
            )
        return {}

    # ── Legacy generators (kept for compatibility, route via narration_client) ──

    def generate_dynamic_world(
        self,
        world: dict[str, Any],
        action: Action,
        validation: dict[str, Any],
        state: GameState,
    ) -> dict[str, Any]:
        content = self._narration_chat(
            [
                {"role": "system", "content": self.dynamic_world_prompt},
                {
                    "role": "user",
                    "content": self._with_director_mode(
                        json.dumps(
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
                        )
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
        content = self._narration_chat(
            [
                {"role": "system", "content": self.open_ended_content_prompt},
                {
                    "role": "user",
                    "content": self._with_director_mode(
                        json.dumps(
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
                        )
                    ),
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
        content = self._narration_chat(
            [
                {"role": "system", "content": self.dynamic_content_prompt},
                {
                    "role": "user",
                    "content": self._with_director_mode(
                        json.dumps(
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
                        )
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
        content = self._narration_chat(
            [
                {"role": "system", "content": self.npc_autonomy_prompt},
                {
                    "role": "user",
                    "content": self._with_director_mode(
                        json.dumps(
                            {
                                "visible_npcs": visible_npcs,
                                "player_action": action,
                                "player_hp": state.player.get("hp", 0),
                                "scene": state.scene,
                                "recent_events": state.recent_events,
                                "turn_id": state.turn_id,
                            },
                            ensure_ascii=False,
                        )
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(content)

    # ── Internal chat helpers ────────────────────────────────────────

    def _intent_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        response = self.intent_client.chat.completions.create(
            model=self.intent_model,
            messages=messages,
            temperature=0.3,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def _narration_chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        if not self._narration_available or self.narration_client is None:
            raise RuntimeError("Narration LLM is not available")
        response = self.narration_client.chat.completions.create(
            model=self.narration_model,
            messages=messages,
            temperature=0.3,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def _with_director_mode(self, content: str) -> str:
        return f"{content}\n\n{self.director_mode_prompt}"

    # Backward-compatible alias
    _chat = _narration_chat


# ── Module-level convenience wrappers ──────────────────────────────────


def parse_intent(player_input: str, state: GameState, llm: LLMClient | None = None) -> Action:
    if llm:
        for attempt in range(LLM_RETRY_ATTEMPTS):
            try:
                return llm.parse_intent(player_input, state)
            except (json.JSONDecodeError, APIError, APIConnectionError, AttributeError):
                logging.getLogger(__name__).warning(
                    "parse_intent LLM attempt %d/%d failed",
                    attempt + 1,
                    LLM_RETRY_ATTEMPTS,
                    exc_info=True,
                )
    return heuristic_parse_intent(player_input, state)


def narrate(
    turn_resolution: TurnResolution,
    state: GameState,
    llm: LLMClient | None = None,
) -> str:
    if llm is not None and getattr(llm, "narration_available", False):
        for attempt in range(LLM_RETRY_ATTEMPTS):
            try:
                text = llm.narrate_turn(turn_resolution)
                if text:
                    return text
            except (APIError, APIConnectionError, AttributeError):
                logging.getLogger(__name__).warning(
                    "narrate LLM attempt %d/%d failed",
                    attempt + 1,
                    LLM_RETRY_ATTEMPTS,
                    exc_info=True,
                )
    return fallback_narration(turn_resolution, state)


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
        "recent_history": snapshot.get("history", []),
        "world_clock": snapshot.get("world_clock", {}),
    }
