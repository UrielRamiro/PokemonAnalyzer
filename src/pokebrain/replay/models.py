from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pokebrain.battle.models import ActionSummary, BattleAction, BattleState
from pokebrain.battle_protocol.events import BattleEvent
from pokebrain.search.policy import WeightedAction


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    battle_id: str
    turn: int
    player_id: str
    battle_state: BattleState
    legal_actions: tuple[BattleAction, ...]
    selected_action: BattleAction
    selected_evaluation: ActionSummary
    alternative_evaluations: tuple[ActionSummary, ...]
    decision_time_ms: float
    reasons: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BattleReplay:
    battle_id: str
    initial_state: BattleState | None
    events: tuple[BattleEvent, ...]
    decisions: tuple[DecisionRecord, ...]
    winner: str | None
    battle_directory: str


@dataclass(frozen=True, slots=True)
class DecisionRegret:
    selected_score: float
    best_available_score: float
    regret: float
    classification: str


class DecisionErrorType(Enum):
    MISSED_KO = "missed_ko"
    ATTACKED_IMMUNITY = "attacked_immunity"
    BAD_SWITCH = "bad_switch"
    FAILED_TO_SWITCH = "failed_to_switch"
    SACRIFICED_WIN_CONDITION = "sacrificed_win_condition"
    IGNORED_HAZARDS = "ignored_hazards"
    UNSAFE_SETUP = "unsafe_setup"
    FAILED_TO_REMOVE_HAZARDS = "failed_to_remove_hazards"
    POOR_MOVE_SELECTION = "poor_move_selection"
    OVERPREDICTION = "overprediction"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TurnEvaluation:
    turn: int
    value_before_action: float
    value_after_action: float
    value_change: float


@dataclass(frozen=True, slots=True)
class PolicyPredictionReview:
    actual_action: BattleAction
    predicted_actions: tuple[WeightedAction, ...]
    actual_probability: float
    covered_top_k: bool


@dataclass(frozen=True, slots=True)
class ReviewedDecision:
    record: DecisionRecord
    regret: DecisionRegret
    error_types: tuple[DecisionErrorType, ...]
    turning_point: TurnEvaluation | None
    policy_prediction: PolicyPredictionReview | None = None


@dataclass(frozen=True, slots=True)
class BattleReview:
    battle_id: str
    winner: str | None
    critical_decisions: tuple[ReviewedDecision, ...]
    turning_points: tuple[TurnEvaluation, ...]
    recurring_error_types: tuple[DecisionErrorType, ...]
    summary: str


@dataclass(frozen=True, slots=True)
class ErrorAggregate:
    error_type: DecisionErrorType
    occurrence_count: int
    losses_with_error: int
    wins_with_error: int
    average_value_loss: float
    affected_matchups: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegressionCase:
    case_id: str
    source_battle_id: str
    source_turn: int
    state: BattleState
    acceptable_actions: tuple[BattleAction, ...]
    forbidden_actions: tuple[BattleAction, ...]
    error_type: DecisionErrorType


@dataclass(frozen=True, slots=True)
class CounterfactualResult:
    initial_action: BattleAction
    simulations: int
    wins: int
    losses: int
    ties: int

    @property
    def estimated_value(self) -> float:
        total = self.wins + self.losses + self.ties
        if total == 0:
            return 0.0
        return (self.wins + 0.5 * self.ties) / total
