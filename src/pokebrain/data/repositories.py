from __future__ import annotations

from contextlib import closing
from functools import lru_cache
from typing import Protocol

from pokebrain.data.connection import connect
from pokebrain.data.models import Ability, BaseStats, Item, Move, PokemonSpecies


class SpeciesRepository(Protocol):
    def get_by_id(self, species_id: str) -> PokemonSpecies | None:
        ...

    def search(self, query: str) -> list[PokemonSpecies]:
        ...

    def list_by_type(self, type_id: str) -> list[PokemonSpecies]:
        ...

    def list_by_generation(self, generation: int) -> list[PokemonSpecies]:
        ...


class SQLiteSpeciesRepository:
    def __init__(self, database_path) -> None:
        self.database_path = database_path

    @lru_cache(maxsize=4096)
    def get_by_id(self, species_id: str) -> PokemonSpecies | None:
        with closing(connect(self.database_path)) as connection:
            with connection:
                row = connection.execute(
                    "SELECT * FROM species WHERE id = ?",
                    (species_id,),
                ).fetchone()
                if row is None:
                    alias = connection.execute(
                        "SELECT target_id FROM aliases WHERE alias = ?",
                        (species_id,),
                    ).fetchone()
                    if alias is None:
                        return None
                    row = connection.execute(
                        "SELECT * FROM species WHERE id = ?",
                        (alias["target_id"],),
                    ).fetchone()
                if row is None:
                    return None
                return self._hydrate(connection, row)

    def search(self, query: str) -> list[PokemonSpecies]:
        pattern = f"%{query}%"
        with closing(connect(self.database_path)) as connection:
            with connection:
                rows = connection.execute(
                    """
                    SELECT DISTINCT species.*
                    FROM species
                    LEFT JOIN aliases ON aliases.target_id = species.id
                    WHERE species.name LIKE ? OR species.id LIKE ? OR aliases.alias LIKE ?
                    ORDER BY species.national_dex_number, species.name
                    LIMIT 25
                    """,
                    (pattern, pattern, pattern),
                ).fetchall()
                return [self._hydrate(connection, row) for row in rows]

    def list_by_type(self, type_id: str) -> list[PokemonSpecies]:
        with closing(connect(self.database_path)) as connection:
            with connection:
                rows = connection.execute(
                    """
                    SELECT species.*
                    FROM species
                    JOIN species_types ON species_types.species_id = species.id
                    WHERE species_types.type_id = ?
                    ORDER BY species.national_dex_number, species.name
                    """,
                    (type_id,),
                ).fetchall()
                return [self._hydrate(connection, row) for row in rows]

    def list_by_generation(self, generation: int) -> list[PokemonSpecies]:
        with closing(connect(self.database_path)) as connection:
            with connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM species
                    WHERE generation = ?
                    ORDER BY national_dex_number, name
                    """,
                    (generation,),
                ).fetchall()
                return [self._hydrate(connection, row) for row in rows]

    def _hydrate(self, connection, row) -> PokemonSpecies:
        types = connection.execute(
            """
            SELECT type_id
            FROM species_types
            WHERE species_id = ?
            ORDER BY slot
            """,
            (row["id"],),
        ).fetchall()
        abilities = connection.execute(
            """
            SELECT slot, ability_id
            FROM species_abilities
            WHERE species_id = ?
            ORDER BY slot
            """,
            (row["id"],),
        ).fetchall()
        stats = connection.execute(
            "SELECT * FROM base_stats WHERE species_id = ?",
            (row["id"],),
        ).fetchone()
        return PokemonSpecies(
            id=row["id"],
            name=row["name"],
            national_dex_number=row["national_dex_number"],
            generation=row["generation"],
            types=tuple(type_row["type_id"] for type_row in types),
            base_stats=BaseStats(
                hp=stats["hp"],
                attack=stats["attack"],
                defense=stats["defense"],
                special_attack=stats["special_attack"],
                special_defense=stats["special_defense"],
                speed=stats["speed"],
            ),
            abilities={ability["slot"]: ability["ability_id"] for ability in abilities},
            height_m=row["height_m"],
            weight_kg=row["weight_kg"],
            base_species=row["base_species"],
            forme=row["forme"],
        )


class _SimpleRepository:
    table: str

    def __init__(self, database_path) -> None:
        self.database_path = database_path

    @lru_cache(maxsize=8192)
    def get_by_id(self, row_id: str):
        with closing(connect(self.database_path)) as connection:
            with connection:
                row = connection.execute(
                    f"SELECT * FROM {self.table} WHERE id = ?",
                    (row_id,),
                ).fetchone()
                return self._hydrate(row) if row is not None else None

    def search(self, query: str):
        with closing(connect(self.database_path)) as connection:
            with connection:
                rows = connection.execute(
                    f"""
                    SELECT *
                    FROM {self.table}
                    WHERE id LIKE ? OR name LIKE ?
                    ORDER BY name
                    LIMIT 25
                    """,
                    (f"%{query}%", f"%{query}%"),
                ).fetchall()
                return [self._hydrate(row) for row in rows]


class SQLiteMoveRepository(_SimpleRepository):
    table = "moves"

    def _hydrate(self, row) -> Move:
        return Move(
            id=row["id"],
            name=row["name"],
            type_id=row["type_id"],
            category=row["category"],
            power=row["power"],
            accuracy=row["accuracy"],
            pp=row["pp"],
            priority=row["priority"],
        )


class SQLiteAbilityRepository(_SimpleRepository):
    table = "abilities"

    def _hydrate(self, row) -> Ability:
        return Ability(id=row["id"], name=row["name"], description=row["description"])


class SQLiteItemRepository(_SimpleRepository):
    table = "items"

    def _hydrate(self, row) -> Item:
        return Item(id=row["id"], name=row["name"], description=row["description"])
