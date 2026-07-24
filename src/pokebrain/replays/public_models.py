from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pokebrain.battle.models import BattleAction
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.replays.public_events import ReplayEvent


@dataclass(frozen=True, slots=True)
class ReplayPokemonId:
    side: str
    roster_index: int


@dataclass(frozen=True, slots=True)
class Boosts:
    attack: int = 0
    defense: int = 0
    special_attack: int = 0
    special_defense: int = 0
    speed: int = 0
    accuracy: int = 0
    evasion: int = 0


@dataclass(frozen=True, slots=True)
class PublicPokemonState:
    replay_id: ReplayPokemonId
    replay_ref: str
    species_id: str | None
    hp_current: int | None
    hp_max: int | None
    hp_fraction: float | None
    status: str | None
    boosts: Boosts
    revealed_moves: frozenset[str]
    revealed_item: str | None
    revealed_ability: str | None
    revealed_tera_type: str | None
    fainted: bool
    active: bool
    trapped: bool = False


@dataclass(frozen=True, slots=True)
class PublicSideState:
    side: str
    pokemon: tuple[PublicPokemonState, ...] = ()
    side_conditions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class FieldState:
    weather: str | None = None
    terrain: str | None = None


@dataclass(frozen=True, slots=True)
class ObservedAction:
    side: str
    action: BattleAction
    pokemon_ref: str
    turn: int


@dataclass(frozen=True, slots=True)
class PublicReplayState:
    turn: int
    sides: tuple[PublicSideState, ...]
    field: FieldState
    pending_actions: tuple[ObservedAction, ...] = ()
    battle_finished: bool = False
    statuses: tuple["ReplayReconstructionStatus", ...] = ()


@dataclass(frozen=True, slots=True)
class ReplaySnapshot:
    replay_id: str
    turn: int
    phase: str
    state: PublicReplayState
    source_line_number: int


@dataclass(frozen=True, slots=True)
class ReconstructedDecision:
    state_before_turn: PublicReplayState
    actual_action: ObservedAction
    legal_actions: tuple[BattleAction, ...] | None
    reconstruction_confidence: str
    missing_information: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PartialPolicyExample:
    observed_state: PublicReplayState
    actual_action: ObservedAction
    candidate_actions: tuple[BattleAction, ...] | None
    missing_information: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedPublicReplay:
    replay_id: str
    format_id: str
    events: tuple[ReplayEvent, ...]
    snapshots: tuple[ReplaySnapshot, ...]
    decisions: tuple[ReconstructedDecision, ...]
    partial_examples: tuple[PartialPolicyExample, ...]
    training_examples: tuple[PolicyTrainingExample, ...] = ()
    statuses: tuple["ReplayReconstructionStatus", ...] = ()


class ReplayReconstructionStatus(Enum):
    COMPLETE = "complete"
    PARTIAL_MISSING_TEAM = "partial_missing_team"
    PARTIAL_MISSING_LEGAL_ACTIONS = "partial_missing_legal_actions"
    UNSUPPORTED_PROTOCOL_EVENT = "unsupported_protocol_event"
    AMBIGUOUS_POKEMON_IDENTITY = "ambiguous_pokemon_identity"
    STATE_INCONSISTENCY = "state_inconsistency"
    UNSUPPORTED_FORMAT = "unsupported_format"


class ReplayStateInvariantError(Exception):
    def __init__(self, replay_id: str, line_number: int, invariant: str) -> None:
        super().__init__(f"{replay_id}: line {line_number}: {invariant}")
        self.replay_id = replay_id
        self.line_number = line_number
        self.invariant = invariant
