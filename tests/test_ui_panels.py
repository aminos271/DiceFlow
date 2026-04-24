import unittest

from diceflow.app.game import Game
from diceflow.app.ui import (
    render_action_hints,
    render_prompt,
    render_scene_panel,
    render_status_panel,
    render_turn_result,
)
from diceflow.core.models import TurnRecord
from diceflow.scripting.loader import load_script


class UIPanelsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game(script=load_script("tomb_entrance"), use_llm=False)

    def test_state_helpers_expose_player_scene_and_visible_entities(self) -> None:
        state = self.game.state

        self.assertEqual(state.get_current_scene_id(), "tomb_entrance")
        self.assertEqual(state.get_inventory_items(), state.player["inventory"])
        self.assertIn("guard_1", state.get_visible_entities())
        self.assertIn("guard_1", state.get_hostile_entities())
        self.assertTrue(any("守卫" in hint or "瀹堝崼" in hint for hint in state.get_available_action_hints()))

    def test_status_scene_and_hints_render_structured_blocks(self) -> None:
        state = self.game.state

        status = render_status_panel(state)
        scene = render_scene_panel(state)
        hints = render_action_hints(state)

        self.assertIn("回合 1", status)
        self.assertIn("❤️", status)
        self.assertIn("🎒", status)
        self.assertIn("🌍 周围", scene)
        self.assertIn("可见实体", scene)
        self.assertIn("💡", hints)

    def test_turn_result_renders_check_summary_and_narration(self) -> None:
        record = TurnRecord(
            turn_id=1,
            player_input="attack guard",
            action={"intent_family": "attack", "target": "guard"},
            validation={"valid": True},
            check={"roll": 15, "dc": 12, "result": "success"},
            state_changes={"events": ["hit"]},
            narration="You hit the guard.",
            summary="attack guard -> success",
        )

        rendered = render_turn_result(record)

        self.assertIn("d20=15", rendered)
        self.assertIn("DC 12", rendered)

    def test_render_prompt_returns_colored_string(self) -> None:
        prompt = render_prompt()
        self.assertIn("⚔", prompt)
        self.assertIn(">>", prompt)


if __name__ == "__main__":
    unittest.main()
