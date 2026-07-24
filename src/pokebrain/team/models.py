from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EVSpread:
    hp: int = 0
    attack: int = 0
    defense: int = 0
    special_attack: int = 0
    special_defense: int = 0
    speed: int = 0


@dataclass(frozen=True, slots=True)
class IVSpread:
    hp: int = 31
    attack: int = 31
    defense: int = 31
    special_attack: int = 31
    special_defense: int = 31
    speed: int = 31


@dataclass(frozen=True, slots=True)
class PokemonSet:
    species_id: str
    nickname: str | None
    item_id: str | None
    ability_id: str | None
    level: int
    nature: str | None
    tera_type: str | None
    moves: tuple[str, ...]
    evs: EVSpread
    ivs: IVSpread = field(default_factory=IVSpread)


@dataclass(frozen=True, slots=True)
class Team:
    format_id: str
    members: tuple[PokemonSet, ...]
