from __future__ import annotations

from dataclasses import dataclass

from pokebrain.battle.models import BattleAction, BattleState
from pokebrain.belief.models import BeliefState
from pokebrain.search.policy import WeightedAction


@dataclass(frozen=True, slots=True)
class PolicyTrainingExample:
    format_id: str
    rating_bucket: str | None
    observed_state: BattleState
    belief_state: BeliefState
    legal_actions: tuple[BattleAction, ...]
    predicted_actions: tuple[WeightedAction, ...]
    actual_action: BattleAction


@dataclass(frozen=True, slots=True)
class PolicyCalibrationMetrics:
    examples: int
    top1_accuracy: float
    top3_coverage: float
    top4_coverage: float
    actual_action_probability: float
    log_loss: float
    brier_score: float
    average_entropy: float
    out_of_search_rate: float


@dataclass(frozen=True, slots=True)
class PolicyDatasetSplit:
    train: tuple[PolicyTrainingExample, ...]
    validation: tuple[PolicyTrainingExample, ...]
    test: tuple[PolicyTrainingExample, ...]
