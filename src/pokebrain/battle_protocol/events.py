from __future__ import annotations

from dataclasses import dataclass


class BattleEvent:
    pass


@dataclass(frozen=True, slots=True)
class TurnEvent(BattleEvent):
    turn: int


@dataclass(frozen=True, slots=True)
class SwitchEvent(BattleEvent):
    pokemon_identifier: str
    details: str
    condition: str


@dataclass(frozen=True, slots=True)
class MoveEvent(BattleEvent):
    pokemon_identifier: str
    move_id: str
    target_identifier: str | None = None


@dataclass(frozen=True, slots=True)
class DamageEvent(BattleEvent):
    pokemon_identifier: str
    condition: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class HealEvent(BattleEvent):
    pokemon_identifier: str
    condition: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class ItemEvent(BattleEvent):
    pokemon_identifier: str
    item_id: str


@dataclass(frozen=True, slots=True)
class AbilityEvent(BattleEvent):
    pokemon_identifier: str
    ability_id: str


@dataclass(frozen=True, slots=True)
class TerastallizeEvent(BattleEvent):
    pokemon_identifier: str
    tera_type: str


@dataclass(frozen=True, slots=True)
class FaintEvent(BattleEvent):
    pokemon_identifier: str


@dataclass(frozen=True, slots=True)
class WeatherEvent(BattleEvent):
    weather: str | None


@dataclass(frozen=True, slots=True)
class SideStartEvent(BattleEvent):
    side_identifier: str
    effect: str


@dataclass(frozen=True, slots=True)
class SideEndEvent(BattleEvent):
    side_identifier: str
    effect: str


@dataclass(frozen=True, slots=True)
class WinEvent(BattleEvent):
    winner: str | None


@dataclass(frozen=True, slots=True)
class UnknownBattleEvent(BattleEvent):
    message_type: str
    raw_line: str
