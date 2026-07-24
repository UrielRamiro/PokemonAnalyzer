from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from pokebrain.battle.models import BattleState


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WeightedValue(Generic[T]):
    value: T
    probability: float


@dataclass(frozen=True, slots=True)
class PokemonBelief:
    species_id: str
    possible_items: tuple[WeightedValue[str], ...]
    possible_abilities: tuple[WeightedValue[str], ...]
    possible_moves: tuple[WeightedValue[str], ...]
    possible_tera_types: tuple[WeightedValue[str], ...]
    revealed_item: str | None = None
    revealed_ability: str | None = None
    revealed_moves: frozenset[str] = frozenset()
    revealed_tera_type: str | None = None


@dataclass(frozen=True, slots=True)
class BeliefState:
    opponent_team: tuple[PokemonBelief, ...]


@dataclass(frozen=True, slots=True)
class DecisionContext:
    observed_state: BattleState
    belief_state: BeliefState


@dataclass(frozen=True, slots=True)
class BeliefSearchConfig:
    maximum_scenarios: int = 4
    minimum_probability: float = 0.05


@dataclass(frozen=True, slots=True)
class OpponentScenario:
    probability: float
    resolved_state: BattleState
    assumptions: tuple[str, ...]


MAX_UNREVEALED_PROBABILITY = 0.85
UNKNOWN_VALUE = "unknown"
