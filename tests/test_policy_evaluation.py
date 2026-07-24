from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActionType, ActivePokemonState, BattleAction, BattleSideState, BattleState
from pokebrain.belief.models import BeliefState
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.policy_evaluation.comparison import PolicyComparisonRunner
from pokebrain.policy_evaluation.metrics import evaluate_predictions
from pokebrain.policy_evaluation.models import PolicyPrediction
from pokebrain.policy_evaluation.predictors import FrequencyPolicyPredictor, HeuristicPolicyPredictor, RandomPolicyPredictor
from pokebrain.policy_evaluation.runner import PolicyEvaluationRunner
from pokebrain.policy_evaluation.serialization import report_to_json, write_json
from pokebrain.replays.models import PolicyExampleMetadata
from pokebrain.search.policy import WeightedAction
from pokebrain.team.models import EVSpread, PokemonSet


class PolicyEvaluationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT_DIR / ".tmp_tests" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_predictors_share_contract_and_return_probability_distribution(self) -> None:
        records = (self._record(1, actual=self._move("earthquake")), self._record(2, actual=self._switch("kingambit")))
        examples = tuple(record.example for record in records)

        for predictor in (RandomPolicyPredictor(), FrequencyPolicyPredictor(examples), HeuristicPolicyPredictor()):
            prediction = predictor.predict(records[0].example)

            self.assertTrue(predictor.name)
            self.assertEqual(len(prediction.ranked_actions), len(prediction.probabilities))
            self.assertAlmostEqual(sum(prediction.probabilities), 1.0, places=6)
            self.assertGreaterEqual(prediction.inference_time_ms, 0.0)

    def test_runner_reports_ranking_calibration_performance_and_buckets(self) -> None:
        records = (
            self._record(1, actual=self._move("earthquake")),
            self._record(2, actual=self._move("swordsdance")),
            self._record(3, actual=self._switch("kingambit")),
        )

        report = PolicyEvaluationRunner().evaluate(FrequencyPolicyPredictor(tuple(record.example for record in records)), records)

        self.assertEqual(report.summary.examples, 3)
        self.assertGreaterEqual(report.summary.top1_accuracy, 0.0)
        self.assertGreaterEqual(report.summary.top3_coverage, report.summary.top1_accuracy)
        self.assertGreaterEqual(report.summary.top5_coverage, report.summary.top3_coverage)
        self.assertEqual(len(report.calibration_curve), 10)
        self.assertIn("setup", dict(report.error_buckets))
        self.assertIn("switch", dict(report.error_buckets))
        self.assertIn("hyper-offense", dict(report.matchup_buckets))

    def test_impossible_actions_and_inspection_cases_are_reported(self) -> None:
        record = self._record(1, actual=self._move("earthquake"))
        illegal = self._move("dracometeor")
        prediction = PolicyPrediction((illegal, self._move("earthquake")), (0.9, 0.1), 1.5)

        report = evaluate_predictions("bad-model", (record,), (prediction,))

        self.assertEqual(report.summary.impossible_actions, 1)
        self.assertEqual(report.summary.top1_accuracy, 0.0)
        self.assertEqual(len(report.inspection_cases), 1)
        self.assertEqual(report.inspection_cases[0].replay_id, "replay-1")
        self.assertEqual(report.inspection_cases[0].actual_probability, 0.1)

    def test_comparison_flags_regression_when_candidate_is_worse(self) -> None:
        records = (self._record(1, actual=self._move("earthquake")),)

        baseline_report, candidate_report, comparison = PolicyComparisonRunner().compare(
            baseline=FixedPredictor("baseline", self._move("earthquake")),
            candidate=FixedPredictor("candidate", self._move("stealthrock")),
            records=records,
        )

        self.assertEqual(baseline_report.summary.top1_accuracy, 1.0)
        self.assertEqual(candidate_report.summary.top1_accuracy, 0.0)
        self.assertLess(comparison.top1_delta, 0.0)
        self.assertTrue(comparison.likely_regression)

    def test_report_serialization_writes_curve_buckets_and_inspection_cases(self) -> None:
        record = self._record(1, actual=self._move("earthquake"))
        prediction = PolicyPrediction((self._move("stealthrock"), self._move("earthquake")), (0.8, 0.2), 0.25)
        report = evaluate_predictions("serializable", (record,), (prediction,))
        path = self.root / "report.json"

        write_json(path, report_to_json(report))
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["summary"]["model_name"], "serializable")
        self.assertEqual(len(payload["calibration_curve"]), 10)
        self.assertEqual(payload["inspection_cases"][0]["actual_action"]["move_id"], "earthquake")

    def _record(self, index: int, *, actual: BattleAction) -> PolicyDatasetRecord:
        legal_actions = (
            self._move("earthquake"),
            self._move("stealthrock"),
            self._move("swordsdance"),
            self._switch("kingambit"),
        )
        predicted = tuple(WeightedAction(action, 1 / len(legal_actions), 0.0) for action in legal_actions)
        example = PolicyTrainingExample(
            format_id="gen9ou",
            rating_bucket=None,
            observed_state=self._state(),
            belief_state=BeliefState(opponent_team=()),
            legal_actions=legal_actions,
            predicted_actions=predicted,
            actual_action=actual,
        )
        return PolicyDatasetRecord(
            metadata=PolicyExampleMetadata(
                replay_id=f"replay-{index}",
                turn_number=index,
                player_side="p1",
                format_id="gen9ou",
                upload_time=100 + index,
                rating_bucket=None,
                parser_version="parser-v1",
                feature_version="policy-features-v1",
                belief_model_version="belief-v1",
            ),
            example=example,
        )

    def _state(self) -> BattleState:
        player = PokemonSet("dragapult", None, None, None, 100, None, None, ("shadowball",), EVSpread())
        opponent = PokemonSet("garchomp", None, None, None, 100, None, None, ("earthquake",), EVSpread())
        kingambit = PokemonSet("kingambit", None, None, None, 100, None, None, (), EVSpread())
        roaring_moon = PokemonSet("roaringmoon", None, None, None, 100, None, None, (), EVSpread())
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=1,
            player=BattleSideState(ActivePokemonState(player, 80), (player,)),
            opponent=BattleSideState(ActivePokemonState(opponent, 100), (opponent, kingambit, roaring_moon)),
        )

    def _move(self, move_id: str) -> BattleAction:
        return BattleAction(ActionType.MOVE, move_id=move_id)

    def _switch(self, target_id: str) -> BattleAction:
        return BattleAction(ActionType.SWITCH, switch_target_id=target_id)


class FixedPredictor:
    def __init__(self, name: str, action: BattleAction) -> None:
        self.name = name
        self.action = action

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        ranked = (self.action, *tuple(action for action in example.legal_actions if action != self.action))
        probability = 1 / len(ranked)
        return PolicyPrediction(ranked, tuple(probability for _action in ranked), 0.0)


if __name__ == "__main__":
    unittest.main()
