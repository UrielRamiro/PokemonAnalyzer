from __future__ import annotations

import time
from collections import Counter

from pokebrain.battle.models import BattleAction
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_evaluation.models import PolicyPrediction
from pokebrain.search.policy import HeuristicOpponentPolicyModel


class RandomPolicyPredictor:
    name = "random"

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        started = time.perf_counter()
        probability = 1 / len(example.legal_actions) if example.legal_actions else 0.0
        return PolicyPrediction(
            ranked_actions=example.legal_actions,
            probabilities=tuple(probability for _action in example.legal_actions),
            inference_time_ms=(time.perf_counter() - started) * 1000,
        )


class FrequencyPolicyPredictor:
    name = "frequency"

    def __init__(self, examples: tuple[PolicyTrainingExample, ...]) -> None:
        self.counts = Counter(example.actual_action for example in examples)

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        started = time.perf_counter()
        ranked = tuple(sorted(example.legal_actions, key=lambda action: self.counts[action], reverse=True))
        total = sum(self.counts[action] for action in ranked)
        if total <= 0:
            probability = 1 / len(ranked) if ranked else 0.0
            probabilities = tuple(probability for _action in ranked)
        else:
            probabilities = tuple(self.counts[action] / total for action in ranked)
        return PolicyPrediction(
            ranked_actions=ranked,
            probabilities=probabilities,
            inference_time_ms=(time.perf_counter() - started) * 1000,
        )


class ActiveSpeciesFrequencyPolicyPredictor:
    name = "frequency-active-species"

    def __init__(self, examples: tuple[PolicyTrainingExample, ...]) -> None:
        self.global_counts = Counter(example.actual_action for example in examples)
        self.species_counts = {
            species_id: Counter(example.actual_action for example in bucket)
            for species_id, bucket in _examples_by_active_species(examples).items()
        }

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        started = time.perf_counter()
        species_id = example.observed_state.opponent.active.set_data.species_id
        counts = self.species_counts.get(species_id) or self.global_counts
        ranked = tuple(sorted(example.legal_actions, key=lambda action: counts[action], reverse=True))
        total = sum(counts[action] for action in ranked)
        if total <= 0:
            probability = 1 / len(ranked) if ranked else 0.0
            probabilities = tuple(probability for _action in ranked)
        else:
            probabilities = tuple(counts[action] / total for action in ranked)
        return PolicyPrediction(
            ranked_actions=ranked,
            probabilities=probabilities,
            inference_time_ms=(time.perf_counter() - started) * 1000,
        )


class HeuristicPolicyPredictor:
    name = "heuristic-v3"

    def __init__(self, policy: HeuristicOpponentPolicyModel | None = None) -> None:
        self.policy = policy or HeuristicOpponentPolicyModel()

    def predict(self, example: PolicyTrainingExample) -> PolicyPrediction:
        started = time.perf_counter()
        predicted = self.policy.predict(example.observed_state, None, example.legal_actions)
        return PolicyPrediction(
            ranked_actions=tuple(item.action for item in predicted),
            probabilities=tuple(item.probability for item in predicted),
            inference_time_ms=(time.perf_counter() - started) * 1000,
        )


def _examples_by_active_species(examples: tuple[PolicyTrainingExample, ...]) -> dict[str, list[PolicyTrainingExample]]:
    grouped: dict[str, list[PolicyTrainingExample]] = {}
    for example in examples:
        species_id = example.observed_state.opponent.active.set_data.species_id
        grouped.setdefault(species_id, []).append(example)
    return grouped
