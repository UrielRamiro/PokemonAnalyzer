from __future__ import annotations

import random
from collections import defaultdict

from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.policy_evaluation.metrics import _summary
from pokebrain.policy_evaluation.models import MetricConfidenceInterval, PolicyComparison, PolicyEvaluationReport, PolicyPredictor
from pokebrain.policy_evaluation.runner import PolicyEvaluationRunner


class PolicyComparisonRunner:
    def compare(
        self,
        *,
        baseline: PolicyPredictor,
        candidate: PolicyPredictor,
        records: tuple[PolicyDatasetRecord, ...],
    ) -> tuple[PolicyEvaluationReport, PolicyEvaluationReport, PolicyComparison]:
        baseline_predictions = tuple(baseline.predict(record.example) for record in records)
        candidate_predictions = tuple(candidate.predict(record.example) for record in records)
        baseline_report = PolicyEvaluationRunner().evaluate_predictions(baseline.name, records, baseline_predictions)
        candidate_report = PolicyEvaluationRunner().evaluate_predictions(candidate.name, records, candidate_predictions)
        comparison = PolicyComparison(
            baseline_name=baseline_report.summary.model_name,
            candidate_name=candidate_report.summary.model_name,
            top1_delta=candidate_report.summary.top1_accuracy - baseline_report.summary.top1_accuracy,
            top3_delta=candidate_report.summary.top3_coverage - baseline_report.summary.top3_coverage,
            log_loss_delta=candidate_report.summary.log_loss - baseline_report.summary.log_loss,
            brier_delta=candidate_report.summary.brier_score - baseline_report.summary.brier_score,
            ece_delta=candidate_report.summary.expected_calibration_error - baseline_report.summary.expected_calibration_error,
            p95_inference_delta_ms=candidate_report.summary.p95_inference_ms - baseline_report.summary.p95_inference_ms,
            confidence_intervals=_bootstrap_delta_intervals(
                records,
                baseline_predictions,
                candidate_predictions,
                baseline.name,
                candidate.name,
            ),
            likely_regression=_likely_regression(baseline_report, candidate_report),
        )
        return baseline_report, candidate_report, comparison


def _likely_regression(baseline: PolicyEvaluationReport, candidate: PolicyEvaluationReport) -> bool:
    return (
        candidate.summary.top1_accuracy < baseline.summary.top1_accuracy
        or candidate.summary.log_loss > baseline.summary.log_loss
        or candidate.summary.expected_calibration_error > baseline.summary.expected_calibration_error
        or candidate.summary.impossible_actions > baseline.summary.impossible_actions
    )


def _bootstrap_delta_intervals(
    records,
    baseline_predictions,
    candidate_predictions,
    baseline_name: str,
    candidate_name: str,
    *,
    iterations: int = 200,
) -> tuple[MetricConfidenceInterval, ...]:
    grouped = defaultdict(list)
    for index, record in enumerate(records):
        grouped[record.metadata.replay_id].append(index)
    group_keys = tuple(sorted(grouped))
    if not records or len(group_keys) <= 1:
        baseline_summary = _summary(baseline_name, records, baseline_predictions)
        candidate_summary = _summary(candidate_name, records, candidate_predictions)
        return (
            _point_interval("top1_delta", candidate_summary.top1_accuracy - baseline_summary.top1_accuracy),
            _point_interval("log_loss_delta", candidate_summary.log_loss - baseline_summary.log_loss),
        )

    rng = random.Random(20260720)
    top1_deltas: list[float] = []
    log_loss_deltas: list[float] = []
    for _iteration in range(iterations):
        sampled_indices: list[int] = []
        for _slot in group_keys:
            sampled_indices.extend(grouped[rng.choice(group_keys)])
        sampled_records = tuple(records[index] for index in sampled_indices)
        sampled_baseline = tuple(baseline_predictions[index] for index in sampled_indices)
        sampled_candidate = tuple(candidate_predictions[index] for index in sampled_indices)
        baseline_summary = _summary(baseline_name, sampled_records, sampled_baseline)
        candidate_summary = _summary(candidate_name, sampled_records, sampled_candidate)
        top1_deltas.append(candidate_summary.top1_accuracy - baseline_summary.top1_accuracy)
        log_loss_deltas.append(candidate_summary.log_loss - baseline_summary.log_loss)

    baseline_summary = _summary(baseline_name, records, baseline_predictions)
    candidate_summary = _summary(candidate_name, records, candidate_predictions)
    return (
        MetricConfidenceInterval(
            "top1_delta",
            candidate_summary.top1_accuracy - baseline_summary.top1_accuracy,
            _percentile(top1_deltas, 0.025),
            _percentile(top1_deltas, 0.975),
        ),
        MetricConfidenceInterval(
            "log_loss_delta",
            candidate_summary.log_loss - baseline_summary.log_loss,
            _percentile(log_loss_deltas, 0.025),
            _percentile(log_loss_deltas, 0.975),
        ),
    )


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * percentile))
    return ordered[index]


def _point_interval(metric_name: str, value: float) -> MetricConfidenceInterval:
    return MetricConfidenceInterval(metric_name, value, value, value)
