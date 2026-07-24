from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class MoveMatchupResult:
    move_id: str
    priority: int
    accuracy: int | None
    minimum_damage: int
    maximum_damage: int
    minimum_percent: float
    maximum_percent: float
    ohko_chance: float
    two_hko_chance: float | None
    expected_damage: float
    expected_damage_percent: float
    classification: str
    is_immune: bool
    is_status_move: bool
    requires_context: bool
    missing_context: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateAction:
    attacker_id: str
    move: MoveMatchupResult
    effective_speed: int


class TurnOrder(Enum):
    A_FIRST = "a_first"
    B_FIRST = "b_first"
    SPEED_TIE = "speed_tie"


@dataclass(frozen=True, slots=True)
class KoRange:
    optimistic_turns: int | None
    guaranteed_turns: int | None


@dataclass(frozen=True, slots=True)
class MatchupSide:
    pokemon_id: str
    calculated_speed: int
    move_results: tuple[MoveMatchupResult, ...]
    best_move: MoveMatchupResult | None
    fastest_ko_turns: int | None
    ko_range: KoRange | None
    has_guaranteed_ohko: bool
    has_possible_ohko: bool


class MatchupVerdict(Enum):
    A_FAVORED = "a_favored"
    B_FAVORED = "b_favored"
    EVEN = "even"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class MatchupAnalysis:
    generation: int
    pokemon_a: MatchupSide
    pokemon_b: MatchupSide
    turn_order: TurnOrder
    verdict: MatchupVerdict
    confidence: float
    reasons: tuple[str, ...]
    limitations: tuple[str, ...]

