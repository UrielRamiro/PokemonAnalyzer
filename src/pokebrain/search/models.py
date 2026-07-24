from __future__ import annotations

from dataclasses import dataclass

from pokebrain.battle.models import BattleAction, BattleState
from pokebrain.battle_protocol.events import BattleEvent


@dataclass(frozen=True, slots=True)
class StateTransition:
    probability: float
    next_state: BattleState
    events: tuple[BattleEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class StateEvaluation:
    total_score: float
    material_score: float
    hp_score: float
    position_score: float
    speed_score: float
    hazard_score: float
    status_score: float
    win_condition_score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchNode:
    state: BattleState
    depth: int
    player_action: BattleAction | None = None
    opponent_action: BattleAction | None = None
    probability: float = 1.0


@dataclass(frozen=True, slots=True)
class SearchedActionValue:
    action: BattleAction
    expected_value: float
    worst_case_value: float
    best_case_value: float


@dataclass(frozen=True, slots=True)
class SearchResult:
    best_action: BattleAction
    value: float
    explored_nodes: int
    depth_reached: int
    action_values: tuple[SearchedActionValue, ...]
    principal_variation: tuple[BattleAction, ...]
    limitations: tuple[str, ...]
    interruption_reason: str = "completed"


@dataclass(frozen=True, slots=True)
class SearchConfig:
    maximum_depth: int = 2
    maximum_nodes: int = 500
    maximum_time_ms: int = 500
    maximum_player_actions: int = 5
    maximum_opponent_actions: int = 5


@dataclass(frozen=True, slots=True)
class ActionProbability:
    action: BattleAction
    probability: float
