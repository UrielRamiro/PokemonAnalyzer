from __future__ import annotations

import math
import random
from collections import defaultdict

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.policy_evaluation.models import (
    CalibrationBin,
    ErrorInspectionCase,
    MetricConfidenceInterval,
    PolicyEvaluationReport,
    PolicyEvaluationSummary,
    PolicyPrediction,
)


def evaluate_predictions(
    model_name: str,
    records: tuple[PolicyDatasetRecord, ...],
    predictions: tuple[PolicyPrediction, ...],
    *,
    calibration_bins: int = 10,
    inspection_limit: int = 20,
    bootstrap_iterations: int = 200,
) -> PolicyEvaluationReport:
    summary = _summary(model_name, records, predictions)
    return PolicyEvaluationReport(
        summary=summary,
        confidence_intervals=_bootstrap_confidence_intervals(model_name, records, predictions, iterations=bootstrap_iterations),
        calibration_curve=_calibration_curve(records, predictions, calibration_bins),
        error_buckets=tuple((name, _summary(f"{model_name}:{name}", bucket_records, bucket_predictions)) for name, bucket_records, bucket_predictions in _buckets(records, predictions, _action_bucket)),
        matchup_buckets=tuple((name, _summary(f"{model_name}:{name}", bucket_records, bucket_predictions)) for name, bucket_records, bucket_predictions in _buckets(records, predictions, _matchup_bucket)),
        inspection_cases=_inspection_cases(records, predictions, inspection_limit),
    )


def _summary(
    model_name: str,
    records: tuple[PolicyDatasetRecord, ...],
    predictions: tuple[PolicyPrediction, ...],
) -> PolicyEvaluationSummary:
    if not records:
        return PolicyEvaluationSummary(model_name, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0)
    top1 = top3 = top5 = impossible = 0
    log_loss = brier = actual_probability_total = entropy_total = 0.0
    inference_times = []
    for record, prediction in zip(records, predictions):
        actual = record.example.actual_action
        ranked = prediction.ranked_actions
        probabilities = prediction.probabilities
        probability = _probability_for(actual, prediction)
        if ranked[:1] == (actual,):
            top1 += 1
        if actual in ranked[:3]:
            top3 += 1
        if actual in ranked[:5]:
            top5 += 1
        impossible += sum(1 for action in ranked if action not in record.example.legal_actions)
        log_loss += -math.log(max(probability, 1e-12))
        brier += _brier(record, prediction)
        actual_probability_total += probability
        entropy_total += -sum(prob * math.log(max(prob, 1e-12)) for prob in probabilities)
        inference_times.append(prediction.inference_time_ms)
    count = len(records)
    return PolicyEvaluationSummary(
        model_name=model_name,
        examples=count,
        top1_accuracy=top1 / count,
        top3_coverage=top3 / count,
        top5_coverage=top5 / count,
        log_loss=log_loss / count,
        brier_score=brier / count,
        expected_calibration_error=_ece(records, predictions),
        average_inference_ms=sum(inference_times) / count,
        p95_inference_ms=_percentile(inference_times, 0.95),
        p99_inference_ms=_percentile(inference_times, 0.99),
        impossible_actions=impossible,
        actual_action_probability=actual_probability_total / count,
        average_entropy=entropy_total / count,
    )


def _calibration_curve(
    records: tuple[PolicyDatasetRecord, ...],
    predictions: tuple[PolicyPrediction, ...],
    bins: int,
) -> tuple[CalibrationBin, ...]:
    grouped: list[list[tuple[float, bool]]] = [[] for _ in range(bins)]
    for record, prediction in zip(records, predictions):
        confidence = prediction.probabilities[0] if prediction.probabilities else 0.0
        correct = bool(prediction.ranked_actions and prediction.ranked_actions[0] == record.example.actual_action)
        index = min(bins - 1, int(confidence * bins))
        grouped[index].append((confidence, correct))
    result = []
    for index, items in enumerate(grouped):
        lower = index / bins
        upper = (index + 1) / bins
        if not items:
            result.append(CalibrationBin(lower, upper, 0, 0.0, 0.0))
            continue
        result.append(
            CalibrationBin(
                lower_bound=lower,
                upper_bound=upper,
                examples=len(items),
                average_confidence=sum(item[0] for item in items) / len(items),
                accuracy=sum(1 for _confidence, correct in items if correct) / len(items),
            )
        )
    return tuple(result)


def _ece(records: tuple[PolicyDatasetRecord, ...], predictions: tuple[PolicyPrediction, ...]) -> float:
    curve = _calibration_curve(records, predictions, 10)
    total = len(records)
    if total == 0:
        return 0.0
    return sum((bin.examples / total) * abs(bin.accuracy - bin.average_confidence) for bin in curve)


def _brier(record: PolicyDatasetRecord, prediction: PolicyPrediction) -> float:
    probabilities = {action: probability for action, probability in zip(prediction.ranked_actions, prediction.probabilities)}
    total = 0.0
    for action in record.example.legal_actions:
        expected = 1.0 if action == record.example.actual_action else 0.0
        total += (probabilities.get(action, 0.0) - expected) ** 2
    return total / len(record.example.legal_actions) if record.example.legal_actions else 0.0


def _probability_for(action: BattleAction, prediction: PolicyPrediction) -> float:
    for predicted, probability in zip(prediction.ranked_actions, prediction.probabilities):
        if predicted == action:
            return probability
    return 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(math.ceil(percentile * len(ordered))) - 1)
    return ordered[index]


def _buckets(records, predictions, classifier):
    grouped = defaultdict(lambda: ([], []))
    for record, prediction in zip(records, predictions):
        key = classifier(record)
        grouped[key][0].append(record)
        grouped[key][1].append(prediction)
    return tuple((key, tuple(value[0]), tuple(value[1])) for key, value in sorted(grouped.items()))


def _action_bucket(record: PolicyDatasetRecord) -> str:
    action = record.example.actual_action
    if action.action_type is ActionType.SWITCH:
        return "switch"
    move_id = action.move_id or ""
    if move_id in {"swordsdance", "nastyplot", "calmmind", "dragondance", "agility"}:
        return "setup"
    if move_id in {"recover", "roost", "moonlight", "synthesis", "slackoff", "softboiled", "painsplit"}:
        return "recovery"
    return "attack"


def _matchup_bucket(record: PolicyDatasetRecord) -> str:
    species = {pokemon.species_id for pokemon in record.example.observed_state.opponent.team}
    if {"pelipper", "barraskewda"} & species:
        return "rain"
    if {"torkoal", "walkingwake"} & species:
        return "sun"
    if {"blissey", "toxapex", "clodsire"} & species:
        return "stall"
    if len(species & {"dragapult", "ironvaliant", "roaringmoon", "kingambit"}) >= 2:
        return "hyper-offense"
    return "balance"


def _inspection_cases(
    records: tuple[PolicyDatasetRecord, ...],
    predictions: tuple[PolicyPrediction, ...],
    limit: int,
) -> tuple[ErrorInspectionCase, ...]:
    cases = []
    for record, prediction in zip(records, predictions):
        top = prediction.ranked_actions[0] if prediction.ranked_actions else None
        if top == record.example.actual_action:
            continue
        cases.append(
            ErrorInspectionCase(
                replay_id=record.metadata.replay_id,
                turn_number=record.metadata.turn_number,
                player_side=record.metadata.player_side,
                actual_action=record.example.actual_action,
                top_prediction=top,
                actual_probability=_probability_for(record.example.actual_action, prediction),
                top_probability=prediction.probabilities[0] if prediction.probabilities else 0.0,
                legal_action_count=len(record.example.legal_actions),
            )
        )
    return tuple(cases[:limit])


def _bootstrap_confidence_intervals(
    model_name: str,
    records: tuple[PolicyDatasetRecord, ...],
    predictions: tuple[PolicyPrediction, ...],
    *,
    iterations: int = 200,
) -> tuple[MetricConfidenceInterval, ...]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        grouped[record.metadata.replay_id].append(index)
    group_keys = tuple(sorted(grouped))
    if not records or len(group_keys) <= 1 or iterations <= 0:
        summary = _summary(model_name, records, predictions)
        return (
            _point_interval("top1_accuracy", summary.top1_accuracy),
            _point_interval("top3_coverage", summary.top3_coverage),
            _point_interval("log_loss", summary.log_loss),
            _point_interval("brier_score", summary.brier_score),
            _point_interval("expected_calibration_error", summary.expected_calibration_error),
        )

    rng = random.Random(20260720)
    samples: dict[str, list[float]] = defaultdict(list)
    for _iteration in range(iterations):
        sampled_indices: list[int] = []
        for _slot in group_keys:
            sampled_indices.extend(grouped[rng.choice(group_keys)])
        sampled_records = tuple(records[index] for index in sampled_indices)
        sampled_predictions = tuple(predictions[index] for index in sampled_indices)
        sampled_summary = _summary(model_name, sampled_records, sampled_predictions)
        samples["top1_accuracy"].append(sampled_summary.top1_accuracy)
        samples["top3_coverage"].append(sampled_summary.top3_coverage)
        samples["log_loss"].append(sampled_summary.log_loss)
        samples["brier_score"].append(sampled_summary.brier_score)
        samples["expected_calibration_error"].append(sampled_summary.expected_calibration_error)

    summary = _summary(model_name, records, predictions)
    estimates = {
        "top1_accuracy": summary.top1_accuracy,
        "top3_coverage": summary.top3_coverage,
        "log_loss": summary.log_loss,
        "brier_score": summary.brier_score,
        "expected_calibration_error": summary.expected_calibration_error,
    }
    return tuple(
        MetricConfidenceInterval(
            metric_name=name,
            estimate=estimate,
            lower_95=_percentile(values, 0.025),
            upper_95=_percentile(values, 0.975),
        )
        for name, estimate in estimates.items()
        for values in (samples[name],)
    )


def _point_interval(metric_name: str, value: float) -> MetricConfidenceInterval:
    return MetricConfidenceInterval(metric_name, value, value, value)
