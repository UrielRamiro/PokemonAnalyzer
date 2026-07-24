from __future__ import annotations

import math

from pokebrain.battle.models import BattleAction
from pokebrain.policy_calibration.models import PolicyCalibrationMetrics, PolicyTrainingExample
from pokebrain.search.policy import WeightedAction


class PolicyCalibrationEvaluator:
    def evaluate(
        self,
        examples: tuple[PolicyTrainingExample, ...],
        *,
        search_top_k: int = 4,
    ) -> PolicyCalibrationMetrics:
        if not examples:
            return PolicyCalibrationMetrics(
                examples=0,
                top1_accuracy=0.0,
                top3_coverage=0.0,
                top4_coverage=0.0,
                actual_action_probability=0.0,
                log_loss=0.0,
                brier_score=0.0,
                average_entropy=0.0,
                out_of_search_rate=0.0,
            )

        top1 = 0
        top3 = 0
        top4 = 0
        out_of_search = 0
        probability_total = 0.0
        log_loss_total = 0.0
        brier_total = 0.0
        entropy_total = 0.0

        for example in examples:
            predicted = example.predicted_actions
            probability = probability_for_action(predicted, example.actual_action)
            ranked_actions = tuple(item.action for item in predicted)
            if ranked_actions[:1] == (example.actual_action,):
                top1 += 1
            if example.actual_action in ranked_actions[:3]:
                top3 += 1
            if example.actual_action in ranked_actions[:4]:
                top4 += 1
            if example.actual_action not in ranked_actions[:search_top_k]:
                out_of_search += 1

            probability_total += probability
            log_loss_total += -math.log(max(probability, 1e-12))
            brier_total += _brier_score(example.legal_actions, predicted, example.actual_action)
            entropy_total += entropy(predicted)

        count = len(examples)
        return PolicyCalibrationMetrics(
            examples=count,
            top1_accuracy=top1 / count,
            top3_coverage=top3 / count,
            top4_coverage=top4 / count,
            actual_action_probability=probability_total / count,
            log_loss=log_loss_total / count,
            brier_score=brier_total / count,
            average_entropy=entropy_total / count,
            out_of_search_rate=out_of_search / count,
        )


def probability_for_action(predicted: tuple[WeightedAction, ...], actual: BattleAction) -> float:
    for item in predicted:
        if item.action == actual:
            return item.probability
    return 0.0


def entropy(predicted: tuple[WeightedAction, ...]) -> float:
    return -sum(item.probability * math.log(max(item.probability, 1e-12)) for item in predicted)


def _brier_score(
    legal_actions: tuple[BattleAction, ...],
    predicted: tuple[WeightedAction, ...],
    actual: BattleAction,
) -> float:
    probabilities = {item.action: item.probability for item in predicted}
    if not legal_actions:
        return 0.0
    total = 0.0
    for action in legal_actions:
        expected = 1.0 if action == actual else 0.0
        total += (probabilities.get(action, 0.0) - expected) ** 2
    return total / len(legal_actions)
