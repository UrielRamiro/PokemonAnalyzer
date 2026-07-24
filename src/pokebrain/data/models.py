from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class BaseStats:
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int


@dataclass(frozen=True, slots=True)
class PokemonSpecies:
    id: str
    name: str
    national_dex_number: int
    generation: int
    types: tuple[str, ...]
    base_stats: BaseStats
    abilities: Mapping[str, str]
    height_m: float
    weight_kg: float
    base_species: str | None = None
    forme: str | None = None


@dataclass(frozen=True, slots=True)
class Move:
    id: str
    name: str
    type_id: str
    category: str
    power: int | None
    accuracy: int | None
    pp: int
    priority: int = 0


@dataclass(frozen=True, slots=True)
class Ability:
    id: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Type:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Format:
    id: str
    name: str
    generation: int
    ruleset: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Learnset:
    species_id: str
    move_id: str
    generation: int


@dataclass(frozen=True, slots=True)
class Alias:
    alias: str
    target_id: str
