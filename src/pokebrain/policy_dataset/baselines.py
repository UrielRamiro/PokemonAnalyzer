from __future__ import annotations

from collections import Counter

from pokebrain.battle.models import BattleAction
from pokebrain.policy_calibration.evaluation import PolicyCalibrationEvaluator
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_dataset.models import BaselineReport, PolicyDatasetRecord
from pokebrain.search.policy import HeuristicOpponentPolicyModel, WeightedAction


class BaselineEvaluator:
    def evaluate(self, records: tuple[PolicyDatasetRecord, ...]) -> BaselineReport:
        examples = tuple(record.example for record in records)
        return BaselineReport(
            random=PolicyCalibrationEvaluator().evaluate(tuple(_random_examples(examples))),
            frequency=PolicyCalibrationEvaluator().evaluate(tuple(_frequency_examples(examples))),
            heuristic=PolicyCalibrationEvaluator().evaluate(tuple(_heuristic_examples(examples))),
        )


def _random_examples(examples: tuple[PolicyTrainingExample, ...]):
    for example in examples:
        probability = 1 / len(example.legal_actions) if example.legal_actions else 0.0
        yield _replace_predictions(
            example,
            tuple(WeightedAction(action, probability, 0.0) for action in example.legal_actions),
        )


def _frequency_examples(examples: tuple[PolicyTrainingExample, ...]):
    counts = Counter(example.actual_action for example in examples)
    for example in examples:
        total = sum(counts[action] for action in example.legal_actions)
        if total <= 0:
            yield from _random_examples((example,))
            continue
        predicted = tuple(
            WeightedAction(action, counts[action] / total, float(counts[action]))
            for action in sorted(example.legal_actions, key=lambda action: counts[action], reverse=True)
        )
        yield _replace_predictions(example, predicted)


def _heuristic_examples(examples: tuple[PolicyTrainingExample, ...]):
    policy = HeuristicOpponentPolicyModel()
    for example in examples:
        yield _replace_predictions(
            example,
            policy.predict(example.observed_state, None, example.legal_actions),
        )


def _replace_predictions(example: PolicyTrainingExample, predicted: tuple[WeightedAction, ...]) -> PolicyTrainingExample:
    return PolicyTrainingExample(
        format_id=example.format_id,
        rating_bucket=example.rating_bucket,
        observed_state=example.observed_state,
        belief_state=example.belief_state,
        legal_actions=example.legal_actions,
        predicted_actions=predicted,
        actual_action=example.actual_action,
    )
