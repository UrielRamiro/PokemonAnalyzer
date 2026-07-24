from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle_protocol import DamageEvent, MoveEvent, TurnEvent, UnknownBattleEvent, WinEvent, parse_protocol_line
from pokebrain.local_agent import LocalBattleAgent


class BattleProtocolTest(unittest.TestCase):
    def test_parses_turn_event(self) -> None:
        event = parse_protocol_line("|turn|7")

        self.assertEqual(event, TurnEvent(turn=7))

    def test_parses_damage_event_with_source(self) -> None:
        event = parse_protocol_line("|-damage|p2a: Dragapult|72/100|[from]|Stealth Rock")

        self.assertEqual(
            event,
            DamageEvent(
                pokemon_identifier="p2a: Dragapult",
                condition="72/100",
                source="Stealth Rock",
            ),
        )

    def test_parses_move_event(self) -> None:
        event = parse_protocol_line("|move|p2a: Dragapult|Draco Meteor|p1a: Great Tusk")

        self.assertEqual(
            event,
            MoveEvent(
                pokemon_identifier="p2a: Dragapult",
                move_id="dracometeor",
                target_identifier="p1a: Great Tusk",
            ),
        )

    def test_tier_line_is_not_treated_as_tie(self) -> None:
        event = parse_protocol_line("|tier|[Gen 9] OU")

        self.assertIsInstance(event, UnknownBattleEvent)

    def test_tie_line_is_result_event(self) -> None:
        event = parse_protocol_line("|tie")

        self.assertEqual(event, WinEvent(winner=None))

    def test_local_agent_uses_legal_team_preview_action(self) -> None:
        response = LocalBattleAgent().handle(
            {
                "type": "decision-request",
                "player": {"requestType": "team-preview"},
                "legal_actions": [{"type": "team", "slot": 1, "order": "1"}],
            }
        )

        self.assertEqual(response["type"], "decision")
        self.assertEqual(response["action"], {"type": "team", "slot": 1, "order": "1"})


if __name__ == "__main__":
    unittest.main()
