from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pokebrain.battle.models import BattleAction
from pokebrain.policy_calibration.models import PolicyTrainingExample


@dataclass(frozen=True, slots=True)
class PolicyPrediction:
    ranked_actions: tuple[BattleAction, ...]
    probabilities: tuple[float, ...]
    inference_time_ms: float


class PolicyPredictor(Protocol):
    name: str

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        ...


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower_bound: float
    upper_bound: float
    examples: int
    average_confidence: float
    accuracy: float


@dataclass(frozen=True, slots=True)
class MetricConfidenceInterval:
    metric_name: str
    estimate: float
    lower_95: float
    upper_95: float


@dataclass(frozen=True, slots=True)
class ErrorInspectionCase:
    replay_id: str
    turn_number: int
    player_side: str
    actual_action: BattleAction
    top_prediction: BattleAction | None
    actual_probability: float
    top_probability: float
    legal_action_count: int


@dataclass(frozen=True, slots=True)
class PolicyEvaluationSummary:
    model_name: str
    examples: int
    top1_accuracy: float
    top3_coverage: float
    top5_coverage: float
    log_loss: float
    brier_score: float
    expected_calibration_error: float
    average_inference_ms: float
    p95_inference_ms: float
    p99_inference_ms: float
    impossible_actions: int
    actual_action_probability: float
    average_entropy: float


@dataclass(frozen=True, slots=True)
class PolicyEvaluationReport:
    summary: PolicyEvaluationSummary
    confidence_intervals: tuple[MetricConfidenceInterval, ...]
    calibration_curve: tuple[CalibrationBin, ...]
    error_buckets: tuple[tuple[str, PolicyEvaluationSummary], ...]
    matchup_buckets: tuple[tuple[str, PolicyEvaluationSummary], ...]
    inspection_cases: tuple[ErrorInspectionCase, ...]


@dataclass(frozen=True, slots=True)
class PolicyComparison:
    baseline_name: str
    candidate_name: str
    top1_delta: float
    top3_delta: float
    log_loss_delta: float
    brier_delta: float
    ece_delta: float
    p95_inference_delta_ms: float
    confidence_intervals: tuple[MetricConfidenceInterval, ...]
    likely_regression: bool
