from __future__ import annotations

from dataclasses import dataclass, field

from pokebrain.team.models import EVSpread, IVSpread, PokemonSet
from pokebrain.team.stat_system import effective_ivs_for_format, evs_for_damage_calculator


StatTable = dict[str, int]


@dataclass(frozen=True, slots=True)
class DamagePokemon:
    species: str
    level: int = 100
    ability: str | None = None
    item: str | None = None
    nature: str | None = None
    evs: StatTable = field(default_factory=dict)
    ivs: StatTable = field(default_factory=dict)
    boosts: StatTable = field(default_factory=dict)
    status: str | None = None
    tera_type: str | None = None
    current_hp: int | None = None

    @classmethod
    def from_team_set(cls, pokemon_set: PokemonSet, format_id: str | None = None) -> "DamagePokemon":
        ivs = effective_ivs_for_format(pokemon_set.ivs, format_id)
        return cls(
            species=pokemon_set.species_id,
            level=pokemon_set.level,
            ability=pokemon_set.ability_id,
            item=pokemon_set.item_id,
            nature=pokemon_set.nature,
            evs=evs_for_damage_calculator(pokemon_set.evs, format_id),
            ivs=ivs_to_stat_table(ivs),
            tera_type=pokemon_set.tera_type,
        )


@dataclass(frozen=True, slots=True)
class FieldState:
    weather: str | None = None
    terrain: str | None = None
    reflect: bool = False
    light_screen: bool = False
    aurora_veil: bool = False
    attacker_tailwind: bool = False
    defender_tailwind: bool = False
    helping_hand: bool = False
    friend_guard: bool = False
    is_doubles: bool = False


@dataclass(frozen=True, slots=True)
class DamageRequest:
    generation: int
    attacker: DamagePokemon | PokemonSet
    defender: DamagePokemon | PokemonSet
    move_id: str
    field: FieldState = field(default_factory=FieldState)
    format_id: str = "unknown"


@dataclass(frozen=True, slots=True)
class DamageResult:
    generation: int
    attacker_id: str
    defender_id: str
    move_id: str
    damage_rolls: tuple[int, ...]
    minimum_damage: int
    maximum_damage: int
    defender_max_hp: int
    minimum_percent: float
    maximum_percent: float
    description: str
    ohko_chance: float
    classification: str


@dataclass(frozen=True, slots=True)
class RawDamageResult:
    rolls: tuple[int, ...]
    minimum_damage: int
    maximum_damage: int
    average_damage: float

    @classmethod
    def from_damage_result(cls, result: DamageResult) -> "RawDamageResult":
        return cls(
            rolls=result.damage_rolls,
            minimum_damage=result.minimum_damage,
            maximum_damage=result.maximum_damage,
            average_damage=sum(result.damage_rolls) / len(result.damage_rolls) if result.damage_rolls else 0.0,
        )


@dataclass(frozen=True, slots=True)
class DamageAssessment:
    raw: RawDamageResult
    minimum_percent: float
    maximum_percent: float
    average_percent: float
    ohko_probability: float
    two_hko_probability: float


def evs_to_stat_table(evs: EVSpread) -> StatTable:
    return {
        "hp": evs.hp,
        "atk": evs.attack,
        "def": evs.defense,
        "spa": evs.special_attack,
        "spd": evs.special_defense,
        "spe": evs.speed,
    }


def ivs_to_stat_table(ivs: IVSpread) -> StatTable:
    return {
        "hp": ivs.hp,
        "atk": ivs.attack,
        "def": ivs.defense,
        "spa": ivs.special_attack,
        "spd": ivs.special_defense,
        "spe": ivs.speed,
    }
