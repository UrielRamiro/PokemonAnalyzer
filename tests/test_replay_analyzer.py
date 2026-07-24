from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActionSummary, ActionType, BattleAction
from pokebrain.replay.detectors import detect_error_types
from pokebrain.replay.loader import ReplayLoader, ReplayStateBuilder
from pokebrain.replay.models import DecisionErrorType
from pokebrain.replay.regression import write_regression_cases
from pokebrain.replay.review import ReplayAnalyzer, TextBattleReviewRenderer
from pokebrain.replay.scoring import calculate_regret


class ReplayAnalyzerTest(unittest.TestCase):
    def test_loads_replay_and_reconstructs_state(self) -> None:
        replay = ReplayLoader().load(ROOT_DIR / "runs" / "2026-07-20" / "benchmark-20260720014317-00001")

        self.assertTrue(replay.decisions)
        state = ReplayStateBuilder().state_at_turn(replay, replay.decisions[0].turn)
        self.assertEqual(state.format_id, "gen9ou")

    def test_calculates_regret_from_alternatives(self) -> None:
        replay = ReplayLoader().load(ROOT_DIR / "runs" / "2026-07-20" / "benchmark-20260720014317-00001")
        record = replay.decisions[0]
        stronger = ActionSummary(
            action=BattleAction(ActionType.MOVE, move_id="better"),
            average_utility=record.selected_evaluation.average_utility + 25,
            worst_case_utility=0,
            best_case_utility=0,
            reasons=(),
            risks=(),
        )
        patched = type(record)(
            **{
                **{field: getattr(record, field) for field in record.__dataclass_fields__},
                "alternative_evaluations": (stronger,),
            }
        )

        regret = calculate_regret(patched)

        self.assertEqual(regret.regret, 25)
        self.assertEqual(regret.classification, "significant")

    def test_detects_attacked_immunity(self) -> None:
        replay = ReplayLoader().load(ROOT_DIR / "runs" / "2026-07-20" / "benchmark-20260720014317-00001")
        record = replay.decisions[0]
        selected = ActionSummary(
            action=BattleAction(ActionType.MOVE, move_id="earthquake"),
            average_utility=-100,
            worst_case_utility=-100,
            best_case_utility=-100,
            reasons=(),
            risks=("The target is immune.",),
        )
        patched = type(record)(
            **{
                **{field: getattr(record, field) for field in record.__dataclass_fields__},
                "selected_action": selected.action,
                "selected_evaluation": selected,
            }
        )

        self.assertIn(DecisionErrorType.ATTACKED_IMMUNITY, detect_error_types(patched))

    def test_review_and_regression_generation(self) -> None:
        replay = ReplayLoader().load(ROOT_DIR / "runs" / "2026-07-20" / "benchmark-20260720014317-00001")
        review = ReplayAnalyzer().review(replay, regret_threshold=0)
        output_dir = ROOT_DIR / ".tmp_tests" / "regressions"
        paths = write_regression_cases(review, output_dir, limit=1)

        self.assertEqual(review.battle_id, "benchmark-20260720014317-00001")
        self.assertLessEqual(len(paths), 1)

    def test_review_includes_policy_prediction_context(self) -> None:
        replay = ReplayLoader().load(ROOT_DIR / "runs" / "2026-07-20" / "benchmark-20260720014317-00001")
        review = ReplayAnalyzer().review(replay, regret_threshold=0)

        self.assertTrue(any(decision.policy_prediction is not None for decision in review.critical_decisions))
        rendered = TextBattleReviewRenderer().render(review)
        self.assertIn("acao adversaria prevista", rendered)


if __name__ == "__main__":
    unittest.main()
