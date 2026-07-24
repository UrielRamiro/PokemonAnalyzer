from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pokebrain.battle.models import BattleAction
from pokebrain.belief.provider import LocalUsageBeliefProvider
from pokebrain.data.manager import DataManager
from pokebrain.policy_calibration.evaluation import PolicyCalibrationEvaluator
from pokebrain.policy_calibration.models import PolicyCalibrationMetrics, PolicyDatasetSplit, PolicyTrainingExample
from pokebrain.policy_calibration.perspective import swap_perspective
from pokebrain.replay.loader import ReplayLoader
from pokebrain.replay.models import BattleReplay
from pokebrain.search.policy import (
    HeuristicOpponentPolicyModel,
    OpponentPolicyConfig,
    PolicyCalibration,
    PolicyProfile,
    PolicyWeights,
)


class PolicyCalibrationPipeline:
    def __init__(
        self,
        data_manager: DataManager | None = None,
        policy_config: OpponentPolicyConfig | None = None,
    ) -> None:
        self.data_manager = data_manager or DataManager()
        self.policy_config = policy_config or OpponentPolicyConfig()
        self.belief_provider = LocalUsageBeliefProvider(self.data_manager)
        self.evaluator = PolicyCalibrationEvaluator()
        self._default_policy = HeuristicOpponentPolicyModel(data_manager=self.data_manager, config=self.policy_config)

    def examples_from_replay(
        self,
        replay: BattleReplay,
        *,
        format_id: str | None = None,
        rating_bucket: str | None = None,
        policy: HeuristicOpponentPolicyModel | None = None,
    ) -> tuple[PolicyTrainingExample, ...]:
        model = policy or self._default_policy
        examples: list[PolicyTrainingExample] = []
        for record in replay.decisions:
            if not _is_trainable_action(record.selected_action):
                continue
            legal_actions = tuple(action for action in record.legal_actions if _is_trainable_action(action))
            if record.selected_action not in legal_actions:
                continue
            observed_state = swap_perspective(record.battle_state)
            belief_state = self.belief_provider.initial_belief(observed_state)
            predicted = model.predict(observed_state, None, legal_actions)
            examples.append(
                PolicyTrainingExample(
                    format_id=format_id or observed_state.format_id,
                    rating_bucket=rating_bucket,
                    observed_state=observed_state,
                    belief_state=belief_state,
                    legal_actions=legal_actions,
                    predicted_actions=predicted,
                    actual_action=record.selected_action,
                )
            )
        return tuple(examples)

    def examples_from_paths(
        self,
        replay_paths: tuple[Path, ...],
        *,
        format_id: str | None = None,
        rating_bucket: str | None = None,
        policy: HeuristicOpponentPolicyModel | None = None,
    ) -> tuple[PolicyTrainingExample, ...]:
        examples: list[PolicyTrainingExample] = []
        loader = ReplayLoader()
        for path in sorted(replay_paths, key=lambda item: str(item)):
            if not (path / "result.json").exists():
                continue
            examples.extend(
                self.examples_from_replay(
                    loader.load(path),
                    format_id=format_id,
                    rating_bucket=rating_bucket,
                    policy=policy,
                )
            )
        return tuple(examples)

    def temporal_split(
        self,
        examples: tuple[PolicyTrainingExample, ...],
        *,
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
    ) -> PolicyDatasetSplit:
        total = len(examples)
        train_end = int(total * train_ratio)
        validation_end = train_end + int(total * validation_ratio)
        return PolicyDatasetSplit(
            train=examples[:train_end],
            validation=examples[train_end:validation_end],
            test=examples[validation_end:],
        )

    def evaluate(self, examples: tuple[PolicyTrainingExample, ...]) -> PolicyCalibrationMetrics:
        return self.evaluator.evaluate(examples, search_top_k=self.policy_config.maximum_actions)

    def fit_profile(
        self,
        examples: tuple[PolicyTrainingExample, ...],
        *,
        format_id: str,
        rating_bucket: str | None = None,
        candidate_temperatures: tuple[float, ...] = (0.45, 0.6, 0.8, 1.0, 1.25, 1.6, 2.0),
        tune_weights: bool = True,
    ) -> PolicyProfile:
        weights = PolicyWeights()
        temperature = self.fit_temperature(examples, weights, candidate_temperatures)
        if tune_weights:
            weights = self.fit_weights(examples, temperature, weights)
            temperature = self.fit_temperature(examples, weights, candidate_temperatures)
        return PolicyProfile(
            format_id=format_id,
            rating_bucket=rating_bucket,
            weights=weights,
            calibration=PolicyCalibration(
                temperature=temperature,
                probability_floor=self.policy_config.minimum_probability,
                tactical_threat_floor=0.01,
            ),
        )

    def fit_temperature(
        self,
        examples: tuple[PolicyTrainingExample, ...],
        weights: PolicyWeights,
        candidates: tuple[float, ...],
    ) -> float:
        if not candidates:
            return self.policy_config.temperature
        scored = [
            (
                self._score_profile(examples, weights=weights, temperature=temperature).log_loss,
                temperature,
            )
            for temperature in candidates
        ]
        return min(scored, key=lambda item: item[0])[1]

    def fit_weights(
        self,
        examples: tuple[PolicyTrainingExample, ...],
        temperature: float,
        base_weights: PolicyWeights,
    ) -> PolicyWeights:
        best_weights = base_weights
        best_loss = self._score_profile(examples, weights=base_weights, temperature=temperature).log_loss
        for field in base_weights.__dataclass_fields__:
            current = getattr(best_weights, field)
            for multiplier in (0.75, 0.9, 1.1, 1.25):
                candidate = replace(best_weights, **{field: current * multiplier})
                loss = self._score_profile(examples, weights=candidate, temperature=temperature).log_loss
                if loss < best_loss:
                    best_loss = loss
                    best_weights = candidate
        return best_weights

    def _score_profile(
        self,
        examples: tuple[PolicyTrainingExample, ...],
        *,
        weights: PolicyWeights,
        temperature: float,
    ) -> PolicyCalibrationMetrics:
        policy = HeuristicOpponentPolicyModel(
            data_manager=self.data_manager,
            config=replace(self.policy_config, temperature=temperature),
            weights=weights,
        )
        rescored = tuple(
            replace(
                example,
                predicted_actions=policy.predict(example.observed_state, None, example.legal_actions),
            )
            for example in examples
        )
        return self.evaluate(rescored)


def _is_trainable_action(action: BattleAction) -> bool:
    return bool(action.move_id and action.move_id not in {"team", "unknown"}) or bool(action.switch_target_id)
