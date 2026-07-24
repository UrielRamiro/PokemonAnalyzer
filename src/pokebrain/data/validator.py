from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pokebrain.data.models import (
    Ability,
    Alias,
    Format,
    Item,
    Learnset,
    Move,
    PokemonSpecies,
    Type,
)


@dataclass(frozen=True, slots=True)
class NormalizedSnapshot:
    species: list[PokemonSpecies]
    moves: list[Move]
    abilities: list[Ability]
    items: list[Item]
    types: list[Type]
    learnsets: list[Learnset]
    formats: list[Format]
    aliases: list[Alias]
    metadata: dict


class IntegrityValidator:
    def validate(self, snapshot: NormalizedSnapshot) -> None:
        self._unique("species", (row.id for row in snapshot.species))
        self._unique("moves", (row.id for row in snapshot.moves))
        self._unique("abilities", (row.id for row in snapshot.abilities))
        self._unique("items", (row.id for row in snapshot.items))
        self._unique("types", (row.id for row in snapshot.types))
        self._unique("formats", (row.id for row in snapshot.formats))
        self._unique("aliases", (row.alias for row in snapshot.aliases))

        species_ids = {row.id for row in snapshot.species}
        move_ids = {row.id for row in snapshot.moves}
        ability_names = {row.name for row in snapshot.abilities}
        type_ids = {row.id for row in snapshot.types}

        for species in snapshot.species:
            if not species.types:
                raise ValueError(f"Species {species.id} has no type.")
            for type_id in species.types:
                if type_id not in type_ids:
                    raise ValueError(f"Species {species.id} references missing type {type_id}.")
            for ability_name in species.abilities.values():
                if ability_name not in ability_names:
                    raise ValueError(
                        f"Species {species.id} references missing ability {ability_name}."
                    )
            if species.base_species and species.base_species not in species_ids:
                raise ValueError(
                    f"Species {species.id} references missing base species "
                    f"{species.base_species}."
                )

        for move in snapshot.moves:
            if move.type_id not in type_ids:
                raise ValueError(f"Move {move.id} references missing type {move.type_id}.")
            if move.pp <= 0:
                raise ValueError(f"Move {move.id} has invalid PP.")

        for learnset in snapshot.learnsets:
            if learnset.species_id not in species_ids:
                raise ValueError(
                    f"Learnset references missing species {learnset.species_id}."
                )
            if learnset.move_id not in move_ids:
                raise ValueError(f"Learnset references missing move {learnset.move_id}.")

    def _unique(self, label: str, ids: Iterable[str]) -> None:
        seen: set[str] = set()
        for value in ids:
            if value in seen:
                raise ValueError(f"Duplicate {label} id: {value}.")
            seen.add(value)

