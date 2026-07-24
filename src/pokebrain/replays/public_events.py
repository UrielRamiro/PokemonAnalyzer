from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReplayEventMetadata:
    line_number: int
    raw_line: str
    turn_number: int | None


class ReplayEvent:
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class TurnStarted(ReplayEvent):
    turn: int
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class MoveUsed(ReplayEvent):
    side: str
    pokemon_ref: str
    move_id: str
    target_ref: str | None
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class PokemonSwitched(ReplayEvent):
    side: str
    pokemon_ref: str
    details: str
    hp_text: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class HpChanged(ReplayEvent):
    pokemon_ref: str
    hp_text: str
    cause: str | None
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class PokemonFainted(ReplayEvent):
    pokemon_ref: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class StatusApplied(ReplayEvent):
    pokemon_ref: str
    status: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class StatusRemoved(ReplayEvent):
    pokemon_ref: str
    status: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class BoostChanged(ReplayEvent):
    pokemon_ref: str
    stat: str
    amount: int
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class AbilityRevealed(ReplayEvent):
    pokemon_ref: str
    ability_id: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class ItemRevealed(ReplayEvent):
    pokemon_ref: str
    item_id: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class ItemConsumed(ReplayEvent):
    pokemon_ref: str
    item_id: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class WeatherChanged(ReplayEvent):
    weather: str | None
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class TerrainChanged(ReplayEvent):
    terrain: str | None
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class SideConditionStarted(ReplayEvent):
    side: str
    condition: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class SideConditionEnded(ReplayEvent):
    side: str
    condition: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class TeraUsed(ReplayEvent):
    pokemon_ref: str
    tera_type: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class BattleEnded(ReplayEvent):
    winner: str | None
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class PokemonPreviewed(ReplayEvent):
    side: str
    details: str
    metadata: ReplayEventMetadata


@dataclass(frozen=True, slots=True)
class UnsupportedReplayEvent(ReplayEvent):
    raw_line: str
    command: str
    metadata: ReplayEventMetadata
