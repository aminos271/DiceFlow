from __future__ import annotations

from diceflow.app.game import build_turn_resolution, Game
from diceflow.core.lorebook import SessionLore
from diceflow.core.state import GameState
from diceflow.scripting.loader import load_script


class FakeGameLLM:
    narration_available = False

    def parse_intent(self, player_input: str, state: GameState) -> dict[str, str]:
        del player_input, state
        return {
            "intent_family": "talk",
            "type": "talk",
            "target": "老板",
            "target_id": "barkeeper",
            "tool": "",
            "tool_id": "",
            "approach_tags": [],
            "method_text": "让老板推荐队友",
            "method": "让老板推荐队友",
        }

    def generate_content_patch(self, context: dict[str, object]) -> dict[str, object]:
        assert context["mode"] == "open_ended"
        return {
            "id": "open_ended_social_companion",
            "events": "角落里的旅人抬了抬手，表示愿意聊聊同行的事。",
            "ops": [
                {
                    "op": "add_entity",
                    "id": "dyn_companion",
                    "entity": {
                        "name": "沉默旅人",
                        "type": "npc",
                        "hp": 4,
                        "max_hp": 4,
                        "tags": ["npc", "dynamic", "friendly"],
                        "metadata": {
                            "allowed_actions": ["talk"],
                            "actions": {
                                "talk": {
                                    "dc": 8,
                                    "outcomes": {
                                        "success": {
                                            "events": ["他点点头，愿意和你谈谈路上的安排。"],
                                        }
                                    },
                                }
                            },
                        },
                    },
                },
                {"op": "set_flag", "key": "runtime.companion_found", "value": True},
            ],
        }


def test_standard_talk_can_trigger_open_ended_companion_generation() -> None:
    game = Game(script=load_script("border_town_tavern"), use_llm=False)
    game.llm = FakeGameLLM()

    record = game.run_turn("让老板推荐队友")

    assert record.check is not None
    assert game.state.flags.get("runtime.companion_found") is True
    assert "dyn_companion" in game.state.entities
    assert any("愿意聊聊同行的事" in event for event in game.state.recent_events)


def test_turn_resolution_includes_recent_history() -> None:
    state = GameState(load_script("border_town_tavern"))
    state.record_turn(
        {
            "turn_id": 1,
            "player_input": "先跟老板打听情况",
            "summary": "talk barkeeper -> success。老板提醒最近不太平。",
        }
    )

    resolution = build_turn_resolution(
        turn_id=2,
        player_input="继续问有没有可靠队友",
        action={"intent_family": "talk", "target_id": "barkeeper"},
        validation={"valid": True, "reason": ""},
        check={"dc": 8, "roll": 12, "result": "success"},
        state_changes={"events": ["老板抬眼看了你一下。"]},
        resolution_kind="standard",
        reason_tags=[],
        state=state,
    )

    assert resolution["recent_history"] == [
        {
            "turn_id": 1,
            "player_input": "先跟老板打听情况",
            "summary": "talk barkeeper -> success。老板提醒最近不太平。",
        }
    ]


def test_turn_resolution_includes_lorebook_entries() -> None:
    state = GameState(load_script("border_town_tavern"))
    lorebook = SessionLore()
    lorebook.create_entry(
        type="character",
        title="沉默旅人",
        summary="一个愿意同行的潜在队友。",
        tags=["derived", "character"],
        source="derived",
        discovered=True,
    )

    resolution = build_turn_resolution(
        turn_id=1,
        player_input="去酒馆招募队友",
        action={"intent_family": "talk", "target_id": "barkeeper"},
        validation={"valid": True, "reason": "dynamic_adjudication"},
        check={"dc": 13, "roll": 20, "result": "critical_success", "dynamic": True},
        state_changes={"events": ["角落里的旅人抬手示意。"]},
        resolution_kind="dynamic_adjudication",
        reason_tags=["social"],
        state=state,
        lorebook=lorebook,
    )

    assert resolution["lorebook_entries"] == [
        {
            "type": "character",
            "title": "沉默旅人",
            "summary": "一个愿意同行的潜在队友。",
            "tags": ["derived", "character"],
            "linked_entity_id": None,
        }
    ]
