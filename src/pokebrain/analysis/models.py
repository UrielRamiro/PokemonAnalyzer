from __future__ import annotations

from dataclasses import dataclass

from pokebrain.showdown import TeamValidationResult


@dataclass(frozen=True, slots=True)
class HazardAnalysis:
    stealth_rock_users: tuple[str, ...]
    spikes_users: tuple[str, ...]
    toxic_spikes_users: tuple[str, ...]
    sticky_web_users: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RemovalMoveUse:
    species_id: str
    move_id: str
    effect: str


@dataclass(frozen=True, slots=True)
class RemovalAnalysis:
    removers: tuple[RemovalMoveUse, ...]


@dataclass(frozen=True, slots=True)
class RecoveryAnalysis:
    reliable: tuple[str, ...]
    conditional: tuple[str, ...]
    draining: tuple[str, ...]
    passive: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PriorityMoveUse:
    species_id: str
    move_id: str
    priority: int


@dataclass(frozen=True, slots=True)
class SpeedEntry:
    species_id: str
    speed: int


@dataclass(frozen=True, slots=True)
class SpeedProfile:
    entries: tuple[SpeedEntry, ...]
    priority: tuple[PriorityMoveUse, ...]


@dataclass(frozen=True, slots=True)
class TypeMatchup:
    attacking_type: str
    multiplier: float


@dataclass(frozen=True, slots=True)
class PokemonTypeProfile:
    species_id: str
    matchups: tuple[TypeMatchup, ...]


@dataclass(frozen=True, slots=True)
class TeamTypeSummary:
    attacking_type: str
    weaknesses: int
    quad_weaknesses: int
    resistances: int
    immunities: int


@dataclass(frozen=True, slots=True)
class TeamTypeProfile:
    members: tuple[PokemonTypeProfile, ...]
    summary: tuple[TeamTypeSummary, ...]


@dataclass(frozen=True, slots=True)
class CalculatedStats:
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    species_id: str
    roles: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeamAnalysis:
    format_id: str
    validation: TeamValidationResult
    parse_errors: tuple[str, ...]
    member_count: int
    hazards: HazardAnalysis
    removal: RemovalAnalysis
    type_profile: TeamTypeProfile
    speed_profile: SpeedProfile
    recovery: RecoveryAnalysis
    roles: tuple[RoleAssignment, ...]
    warnings: tuple[str, ...]

