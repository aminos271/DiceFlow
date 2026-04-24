import unittest

from diceflow.core.state import GameState
from diceflow.core.updater import update_state
from diceflow.core.validator import validate
from diceflow.scripting.archetypes import materialize_entity
from diceflow.scripting.loader import load_script


class EntityArchetypesTest(unittest.TestCase):
    def test_npc_archetype_has_social_state_inventory_and_attributes(self) -> None:
        npc = materialize_entity(
            {
                "type": "npc",
                "name": "流浪商人",
                "aliases": ["商人"],
                "inventory": ["old_coin"],
                "favorability": 1,
                "attributes": {"charm": 12},
            },
            "merchant_1",
        )

        self.assertEqual(npc["favorability"], 1)
        self.assertEqual(npc["disposition"], "neutral")
        self.assertEqual(npc["inventory"], ["old_coin"])
        self.assertEqual(npc["attributes"]["strength"], 10)
        self.assertEqual(npc["attributes"]["charm"], 12)
        self.assertIn("talk", npc["metadata"]["allowed_actions"])
        self.assertIn("attack", npc["metadata"]["actions"])

    def test_item_archetype_can_be_spawned_and_taken(self) -> None:
        state = GameState(load_script("tomb_entrance"))
        state.apply_changes(
            {
                "spawn_entities": {
                    "silver_ring": {
                        "type": "item",
                        "name": "银戒指",
                        "aliases": ["戒指"],
                        "item_id": "银戒指",
                        "source": "merchant_1",
                        "value": 20,
                        "rarity": "uncommon",
                        "effects": [{"kind": "social_hint", "value": 1}],
                    }
                }
            }
        )

        ring = state.entities["silver_ring"]
        self.assertEqual(ring["source"], "merchant_1")
        self.assertEqual(ring["value"], 20)
        self.assertEqual(ring["rarity"], "uncommon")
        self.assertEqual(ring["effects"], [{"kind": "social_hint", "value": 1}])

        action = {"type": "take", "target": "戒指", "method": "拿起戒指", "tool": ""}
        self.assertTrue(validate(action, state)["valid"])
        self.assertEqual(action["target_id"], "silver_ring")

        changes = update_state(action, {"result": "success"}, state)
        state.apply_changes(changes)

        self.assertIn("银戒指", state.player["inventory"])
        self.assertTrue(state.entities["silver_ring"]["looted"])


if __name__ == "__main__":
    unittest.main()
