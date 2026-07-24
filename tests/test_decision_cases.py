from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle import MoveDecisionEngine, battle_state_from_dict
from pokebrain.battle.models import ActionType, BattleAction


class DecisionCaseTest(unittest.TestCase):
    def test_decision_cases(self) -> None:
        for path in sorted((ROOT_DIR / "benchmarks" / "decision_cases").glob("*.json")):
            with self.subTest(case=path.stem):
                with path.open("r", encoding="utf-8") as file:
                    case = json.load(file)
                state = battle_state_from_dict(case["state"])
                decision = MoveDecisionEngine().decide(state)
                recommended = decision.recommended_action
                acceptable = tuple(_action_from_dict(action) for action in case["acceptable_actions"])
                forbidden = tuple(_action_from_dict(action) for action in case["forbidden_actions"])

                if acceptable:
                    self.assertIn(recommended, acceptable)
                self.assertNotIn(recommended, forbidden)


def _action_from_dict(data: dict) -> BattleAction:
    if data["type"] == "move":
        return BattleAction(ActionType.MOVE, move_id=data["move_id"])
    if data["type"] == "switch":
        return BattleAction(ActionType.SWITCH, switch_target_id=data["switch_target_id"])
    raise ValueError(f"Unknown action type: {data['type']}")


if __name__ == "__main__":
    unittest.main()
