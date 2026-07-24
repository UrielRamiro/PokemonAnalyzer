from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from pokebrain.battle.models import BattleAction
from pokebrain.replays.public_models import ObservedAction, PartialPolicyExample, PublicReplayState, ReplaySnapshot
from pokebrain.team.models import PokemonSet, Team


T = TypeVar("T")


class EvidenceSource(str, Enum):
    AUTHORITATIVE_RUNNER = "authoritative_runner"
    TEAM_EXPORT = "team_export"
    FORMAT_DEFINED_SET = "format_defined_set"
    PUBLIC_REPLAY_LOG = "public_replay_log"
    STATISTICAL_INFERENCE = "statistical_inference"


class EvidenceConfidence(str, Enum):
    AUTHORITATIVE = "authoritative"
    OBSERVED = "observed"
    DERIVED = "derived"
    INFERRED = "inferred"


@dataclass(frozen=True, slots=True)
class EvidenceValue(Generic[T]):
    value: T
    source: EvidenceSource
    confidence: EvidenceConfidence
    first_known_turn: int | None


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    field: str
    authoritative_value: object | None
    observed_value: object | None
    replay_id: str
    turn: int | None


@dataclass(frozen=True, slots=True)
class AuthoritativeMoveSet:
    moves: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WeightedMoveSet:
    moves: tuple[str, ...]
    probability: float


@dataclass(frozen=True, slots=True)
class HypothesizedMoveSet:
    candidates: tuple[WeightedMoveSet, ...]


@dataclass(frozen=True, slots=True)
class ResolvedPokemon:
    set_data: PokemonSet
    species: EvidenceValue[str]
    moves: EvidenceValue[AuthoritativeMoveSet] | EvidenceValue[HypothesizedMoveSet]
    item: EvidenceValue[str | None]
    ability: EvidenceValue[str | None]
    tera_type: EvidenceValue[str | None]


@dataclass(frozen=True, slots=True)
class ResolvedTeam:
    side: str
    team: Team
    members: tuple[ResolvedPokemon, ...]
    source: EvidenceSource


@dataclass(frozen=True, slots=True)
class ReplayArtifactBundle:
    authoritative_battle_record: object | None = None
    player_1_team_export: str | None = None
    player_2_team_export: str | None = None
    format_defined_sets: object | None = None


@dataclass(frozen=True, slots=True)
class PublicKnowledge:
    side: str
    revealed_moves: tuple[EvidenceValue[str], ...]
    revealed_items: tuple[EvidenceValue[str], ...]
    revealed_abilities: tuple[EvidenceValue[str], ...]


@dataclass(frozen=True, slots=True)
class DecisionKnowledge:
    actor_authoritative_team: ResolvedTeam | None
    actor_public_knowledge: PublicKnowledge
    opponent_public_knowledge: PublicKnowledge


@dataclass(frozen=True, slots=True)
class TeamResolutionResult:
    player_1_team: ResolvedTeam | None
    player_2_team: ResolvedTeam | None
    unresolved_reasons: tuple[str, ...]
    conflicts: tuple[EvidenceConflict, ...]


class LegalActionQuality(str, Enum):
    AUTHORITATIVE = "authoritative"
    RECONSTRUCTED_COMPLETE = "reconstructed_complete"
    RECONSTRUCTED_PARTIAL = "reconstructed_partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class LegalActionSet:
    actions: tuple[BattleAction, ...]
    quality: LegalActionQuality
    evidence_sources: tuple[EvidenceSource, ...]
    missing_constraints: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnrichedPolicyExample:
    snapshot: ReplaySnapshot
    actual_action: ObservedAction
    decision_knowledge: DecisionKnowledge
    legal_actions: LegalActionSet
    partial_example: PartialPolicyExample | None


@dataclass(slots=True)
class LegalActionDiffMetrics:
    exact_matches: int = 0
    missing_actions: int = 0
    extra_actions: int = 0
    actual_action_missing: int = 0
