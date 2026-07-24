from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pokebrain.team.models import PokemonSet


@dataclass(frozen=True, slots=True)
class ActivePokemonState:
    set_data: PokemonSet
    current_hp: int
    status: str | None = None
    attack_stage: int = 0
    defense_stage: int = 0
    special_attack_stage: int = 0
    special_defense_stage: int = 0
    speed_stage: int = 0
    confused: bool = False
    trapped: bool = False


@dataclass(frozen=True, slots=True)
class BattleSideState:
    active: ActivePokemonState
    team: tuple[PokemonSet, ...]
    fainted_ids: tuple[str, ...] = ()
    stealth_rock: bool = False
    spikes_layers: int = 0
    toxic_spikes_layers: int = 0
    sticky_web: bool = False


@dataclass(frozen=True, slots=True)
class BattleState:
    generation: int
    format_id: str
    turn: int
    player: BattleSideState
    opponent: BattleSideState
    weather: str | None = None
    terrain: str | None = None
    trick_room_turns: int = 0


class ActionType(Enum):
    MOVE = "move"
    SWITCH = "switch"


@dataclass(frozen=True, slots=True)
class BattleAction:
    action_type: ActionType
    move_id: str | None = None
    switch_target_id: str | None = None
    action_id: str | None = None


@dataclass(frozen=True, slots=True)
class ActionEvaluation:
    action: BattleAction
    score: float
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation:
    player_action: BattleAction
    opponent_action: BattleAction
    utility: float


@dataclass(frozen=True, slots=True)
class ActionSummary:
    action: BattleAction
    average_utility: float
    worst_case_utility: float
    best_case_utility: float
    reasons: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MoveDecision:
    recommended_action: BattleAction
    alternatives: tuple[ActionSummary, ...]
    confidence: float
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    limitations: tuple[str, ...]
