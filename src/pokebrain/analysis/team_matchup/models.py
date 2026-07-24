from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pokebrain.analysis.matchup import MatchupAnalysis


@dataclass(frozen=True, slots=True)
class MatchupCell:
    pokemon_a_id: str
    pokemon_b_id: str
    analysis: MatchupAnalysis


@dataclass(frozen=True, slots=True)
class TeamMatchupMatrix:
    team_a_ids: tuple[str, ...]
    team_b_ids: tuple[str, ...]
    cells: tuple[MatchupCell, ...]


@dataclass(frozen=True, slots=True)
class MatchupScore:
    advantage: float
    confidence: float
    uncertain: bool

    @property
    def weighted_score(self) -> float:
        return self.advantage * self.confidence


@dataclass(frozen=True, slots=True)
class PokemonMatchupSummary:
    pokemon_id: str
    favorable_against: tuple[str, ...]
    unfavorable_against: tuple[str, ...]
    even_against: tuple[str, ...]
    uncertain_against: tuple[str, ...]
    coverage_score: float


@dataclass(frozen=True, slots=True)
class ThreatAssessment:
    threat_id: str
    favorable_answers: tuple[str, ...]
    neutral_answers: tuple[str, ...]
    unfavorable_answers: tuple[str, ...]
    severity: str


class ResponseType(Enum):
    DIRECTLY_FAVORED = "directly_favored"
    POSSIBLE_CHECK = "possible_check"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class SwitchInAnalysis:
    defender_id: str
    attacker_id: str
    safe_against_moves: tuple[str, ...]
    unsafe_against_moves: tuple[str, ...]
    survives_best_move: bool
    survives_two_hits: bool
    classification: str


@dataclass(frozen=True, slots=True)
class TeamMatchupAnalysis:
    generation: int
    matrix: TeamMatchupMatrix
    team_a_summaries: tuple[PokemonMatchupSummary, ...]
    team_b_summaries: tuple[PokemonMatchupSummary, ...]
    threats_to_team_a: tuple[ThreatAssessment, ...]
    threats_to_team_b: tuple[ThreatAssessment, ...]
    overall_score_for_team_a: float
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]

