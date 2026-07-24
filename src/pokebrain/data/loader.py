from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokebrain.data.models import (
    Ability,
    Alias,
    BaseStats,
    Format,
    Item,
    Learnset,
    Move,
    PokemonSpecies,
    Type,
)


class NormalizedDataLoader:
    def __init__(self, snapshot_dir: Path | str) -> None:
        self.snapshot_dir = Path(snapshot_dir)

    def species(self) -> list[PokemonSpecies]:
        return [self._species(row) for row in self._read("species.json")]

    def moves(self) -> list[Move]:
        return [self._move(row) for row in self._read("moves.json")]

    def abilities(self) -> list[Ability]:
        return [
            Ability(
                id=row["id"],
                name=row["name"],
                description=row.get("description"),
            )
            for row in self._read("abilities.json")
        ]

    def items(self) -> list[Item]:
        return [
            Item(
                id=row["id"],
                name=row["name"],
                description=row.get("description"),
            )
            for row in self._read("items.json")
        ]

    def types(self) -> list[Type]:
        path = self.snapshot_dir / "types.json"
        if path.exists():
            return [Type(id=row["id"], name=row["name"]) for row in self._read("types.json")]

        type_ids = {
            type_id
            for species in self.species()
            for type_id in species.types
        }
        type_ids.update(move.type_id for move in self.moves())
        return [Type(id=type_id, name=type_id) for type_id in sorted(type_ids)]

    def learnsets(self) -> list[Learnset]:
        return [
            Learnset(
                species_id=row["pokemon_id"],
                move_id=row["move_id"],
                generation=row["generation"],
            )
            for row in self._read("learnsets.json")
        ]

    def formats(self) -> list[Format]:
        return [
            Format(
                id=row["id"],
                name=row["name"],
                generation=row["generation"],
                ruleset=tuple(row.get("ruleset", ())),
            )
            for row in self._read("formats.json")
        ]

    def aliases(self) -> list[Alias]:
        return [
            Alias(alias=row["alias"], target_id=row["target_id"])
            for row in self._read("aliases.json")
        ]

    def metadata(self) -> dict[str, Any]:
        path = self.snapshot_dir / "metadata.json"
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError("metadata.json must contain an object.")
        return data

    def _species(self, row: dict[str, Any]) -> PokemonSpecies:
        stats = row["base_stats"]
        return PokemonSpecies(
            id=row["id"],
            name=row["name"],
            national_dex_number=row["national_dex"],
            generation=row["generation"],
            types=tuple(row["types"]),
            base_stats=BaseStats(
                hp=stats["hp"],
                attack=stats["atk"],
                defense=stats["def"],
                special_attack=stats["spa"],
                special_defense=stats["spd"],
                speed=stats["spe"],
            ),
            abilities={
                slot: ability
                for slot, ability in row["abilities"].items()
                if ability
            },
            height_m=row["height_m"],
            weight_kg=row["weight_kg"],
            base_species=row.get("base_species"),
            forme=row.get("forme"),
        )

    def _move(self, row: dict[str, Any]) -> Move:
        return Move(
            id=row["id"],
            name=row["name"],
            type_id=row["type"],
            category=row["category"],
            power=row.get("power"),
            accuracy=row.get("accuracy"),
            pp=row["pp"],
            priority=row.get("priority", 0),
        )

    def _read(self, filename: str) -> list[dict[str, Any]]:
        path = self.snapshot_dir / filename
        if not path.exists():
            return []

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, list):
            raise ValueError(f"{path} must contain a JSON list.")

        return data
