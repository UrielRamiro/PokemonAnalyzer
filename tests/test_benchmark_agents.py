from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.benchmark.agents import PreviousVersionAgent, RandomAgent, create_battle_agent


class BenchmarkAgentsTest(unittest.TestCase):
    def test_random_agent_picks_legal_action(self) -> None:
        action = RandomAgent(seed=1).decide(
            {
                "legal_actions": [
                    {"type": "move", "slot": 1, "moveId": "tackle"},
                    {"type": "switch", "slot": 2, "switchSpeciesId": "mew"},
                ]
            }
        )["action"]

        self.assertIn(action["type"], {"move", "switch"})

    def test_previous_version_agent_is_available(self) -> None:
        agent = create_battle_agent("previous-version")

        self.assertIsInstance(agent, PreviousVersionAgent)
        self.assertEqual(agent.name, "previous-version")

    def test_policy_search_ranks_team_preview_orders(self) -> None:
        agent = create_battle_agent("search-v3-policy")
        response = agent.decide(
            {
                "player": {
                    "requestType": "team-preview",
                    "team": [
                        self._pokemon(1, "hydreigon", 98, ("darkpulse", "protect")),
                        self._pokemon(2, "mamoswine", 80, ("earthquake", "protect")),
                        self._pokemon(3, "incineroar", 80, ("fakeout", "partingshot")),
                        self._pokemon(4, "whimsicott", 184, ("tailwind", "moonblast")),
                        self._pokemon(5, "garchomp", 169, ("earthquake", "rockslide", "protect")),
                        self._pokemon(6, "kingambit", 70, ("suckerpunch", "kowtowcleave", "protect")),
                    ],
                },
                "opponent": {"team": []},
                "legal_actions": [
                    {"type": "team", "slot": 1, "order": "1234"},
                    {"type": "team", "slot": 2, "order": "3415"},
                    {"type": "team", "slot": 3, "order": "3456"},
                ],
            }
        )

        self.assertEqual(response["action"]["order"], "3456")
        self.assertEqual(response["metrics"]["search_interruption_reason"], "vgc_team_preview_search")
        self.assertFalse(response["metrics"]["search_fallback_used"])

    def test_policy_search_contests_sun_in_team_preview(self) -> None:
        agent = create_battle_agent("search-v3-policy")
        response = agent.decide(
            {
                "player": {
                    "requestType": "team-preview",
                    "team": [
                        self._pokemon(1, "pelipper", 117, ("tailwind", "wideguard", "protect"), ability="drizzle"),
                        self._pokemon(2, "palafin", 136, ("wavecrash", "aquajet", "protect")),
                        self._pokemon(3, "hydreigon", 98, ("darkpulse", "protect")),
                        self._pokemon(4, "chandelure", 100, ("heatwave", "protect")),
                        self._pokemon(5, "incineroar", 80, ("fakeout", "partingshot")),
                        self._pokemon(6, "kingambit", 70, ("suckerpunch", "kowtowcleave", "protect")),
                    ],
                },
                "opponent": {
                    "team": [
                        self._pokemon(1, "charizardmegay", 146, ("heatwave", "solarbeam"), ability="drought"),
                        self._pokemon(2, "venusaur", 145, ("sleeppowder", "weatherball"), ability="chlorophyll"),
                    ]
                },
                "legal_actions": [
                    {"type": "team", "slot": 1, "order": "3456"},
                    {"type": "team", "slot": 2, "order": "1256"},
                ],
            }
        )

        self.assertEqual(response["action"]["order"], "1256")

    def test_policy_search_avoids_unsupported_fragile_lead(self) -> None:
        agent = create_battle_agent("search-v3-policy")
        response = agent.decide(
            {
                "player": {
                    "requestType": "team-preview",
                    "team": [
                        self._pokemon(1, "vivillon", 109, ("sleeppowder", "protect")),
                        self._pokemon(2, "chandelure", 100, ("heatwave", "protect")),
                        self._pokemon(3, "incineroar", 80, ("fakeout", "partingshot")),
                        self._pokemon(4, "whimsicott", 184, ("tailwind", "moonblast")),
                    ],
                },
                "opponent": {"team": [self._pokemon(1, "weavile", 194, ("fakeout", "iciclecrash"))]},
                "legal_actions": [
                    {"type": "team", "slot": 1, "order": "1234"},
                    {"type": "team", "slot": 2, "order": "3412"},
                ],
            }
        )

        self.assertEqual(response["action"]["order"], "3412")

    def _pokemon(self, slot: int, species: str, speed: int, moves: tuple[str, ...], ability: str | None = None):
        return {
            "slot": slot,
            "speciesId": species,
            "condition": "100/100",
            "active": False,
            "stats": {"spe": speed},
            "moves": list(moves),
            "abilityId": ability,
        }


if __name__ == "__main__":
    unittest.main()
