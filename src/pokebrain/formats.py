from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class MechanicsRules:
    allows_tera: bool
    allows_dynamax: bool
    allows_megas: bool
    allows_z_moves: bool


@dataclass(frozen=True, slots=True)
class FormatRules:
    format_id: str
    game_id: str
    generation: int
    battle_type: str
    active_slots_per_side: int
    registered_team_size: int
    selected_team_size: int
    default_level: int
    mechanics: MechanicsRules


@dataclass(frozen=True, slots=True)
class Regulation:
    regulation_id: str
    game_id: str
    format_id: str
    valid_from: date
    valid_until: date | None
    allowed_species: frozenset[str]
    banned_species: frozenset[str]
    restricted_pokemon_limit: int
    mythical_allowed: bool
    item_clause: bool
    species_clause: bool
    mechanics: MechanicsRules


GEN9_OU_RULES = FormatRules(
    format_id="gen9ou",
    game_id="sv",
    generation=9,
    battle_type="singles",
    active_slots_per_side=1,
    registered_team_size=6,
    selected_team_size=6,
    default_level=100,
    mechanics=MechanicsRules(
        allows_tera=True,
        allows_dynamax=False,
        allows_megas=False,
        allows_z_moves=False,
    ),
)
