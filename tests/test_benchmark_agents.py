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


if __name__ == "__main__":
    unittest.main()
