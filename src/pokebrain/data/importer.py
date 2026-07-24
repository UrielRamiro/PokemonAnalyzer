from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path

from pokebrain.data.connection import connect
from pokebrain.data.loader import NormalizedDataLoader
from pokebrain.data.schema import clear_database, initialize_database
from pokebrain.data.validator import IntegrityValidator, NormalizedSnapshot


class SQLiteImporter:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)

    def import_snapshot(self, snapshot_dir: Path | str) -> NormalizedSnapshot:
        loader = NormalizedDataLoader(snapshot_dir)
        snapshot = NormalizedSnapshot(
            species=loader.species(),
            moves=loader.moves(),
            abilities=loader.abilities(),
            items=loader.items(),
            types=loader.types(),
            learnsets=loader.learnsets(),
            formats=loader.formats(),
            aliases=loader.aliases(),
            metadata=loader.metadata(),
        )
        IntegrityValidator().validate(snapshot)

        with closing(connect(self.database_path)) as connection:
            with connection:
                initialize_database(connection)
                clear_database(connection)
                self._insert_types(connection, snapshot.types)
                self._insert_abilities(connection, snapshot.abilities)
                self._insert_items(connection, snapshot.items)
                self._insert_moves(connection, snapshot.moves)
                self._insert_species(connection, snapshot.species)
                self._insert_learnsets(connection, snapshot.learnsets)
                self._insert_formats(connection, snapshot.formats)
                self._insert_aliases(connection, snapshot.aliases)
                self._insert_metadata(connection, snapshot.metadata)

        return snapshot

    def _insert_species(self, connection, species_rows) -> None:
        connection.executemany(
            """
            INSERT INTO species (
                id, name, national_dex_number, generation, height_m, weight_kg,
                base_species, forme
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.id,
                    row.name,
                    row.national_dex_number,
                    row.generation,
                    row.height_m,
                    row.weight_kg,
                    row.base_species,
                    row.forme,
                )
                for row in species_rows
            ],
        )
        connection.executemany(
            "INSERT INTO species_types (species_id, slot, type_id) VALUES (?, ?, ?)",
            [
                (row.id, index, type_id)
                for row in species_rows
                for index, type_id in enumerate(row.types)
            ],
        )
        connection.executemany(
            """
            INSERT INTO species_abilities (species_id, slot, ability_id)
            VALUES (?, ?, ?)
            """,
            [
                (row.id, slot, ability_name)
                for row in species_rows
                for slot, ability_name in row.abilities.items()
            ],
        )
        connection.executemany(
            """
            INSERT INTO base_stats (
                species_id, hp, attack, defense, special_attack, special_defense, speed
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.id,
                    row.base_stats.hp,
                    row.base_stats.attack,
                    row.base_stats.defense,
                    row.base_stats.special_attack,
                    row.base_stats.special_defense,
                    row.base_stats.speed,
                )
                for row in species_rows
            ],
        )

    def _insert_moves(self, connection, rows) -> None:
        connection.executemany(
            """
            INSERT INTO moves (id, name, type_id, category, power, accuracy, pp, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.id,
                    row.name,
                    row.type_id,
                    row.category,
                    row.power,
                    row.accuracy,
                    row.pp,
                    row.priority,
                )
                for row in rows
            ],
        )

    def _insert_abilities(self, connection, rows) -> None:
        connection.executemany(
            "INSERT INTO abilities (id, name, description) VALUES (?, ?, ?)",
            [(row.id, row.name, row.description) for row in rows],
        )

    def _insert_items(self, connection, rows) -> None:
        connection.executemany(
            "INSERT INTO items (id, name, description) VALUES (?, ?, ?)",
            [(row.id, row.name, row.description) for row in rows],
        )

    def _insert_types(self, connection, rows) -> None:
        connection.executemany(
            "INSERT INTO types (id, name) VALUES (?, ?)",
            [(row.id, row.name) for row in rows],
        )

    def _insert_learnsets(self, connection, rows) -> None:
        connection.executemany(
            """
            INSERT INTO learnsets (species_id, move_id, generation)
            VALUES (?, ?, ?)
            """,
            [(row.species_id, row.move_id, row.generation) for row in rows],
        )

    def _insert_formats(self, connection, rows) -> None:
        connection.executemany(
            "INSERT INTO formats (id, name, generation) VALUES (?, ?, ?)",
            [(row.id, row.name, row.generation) for row in rows],
        )
        connection.executemany(
            "INSERT INTO format_rules (format_id, slot, rule_id) VALUES (?, ?, ?)",
            [
                (row.id, index, rule_id)
                for row in rows
                for index, rule_id in enumerate(row.ruleset)
            ],
        )

    def _insert_aliases(self, connection, rows) -> None:
        connection.executemany(
            "INSERT INTO aliases (alias, target_id) VALUES (?, ?)",
            [(row.alias, row.target_id) for row in rows],
        )

    def _insert_metadata(self, connection, metadata: dict) -> None:
        connection.executemany(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            [(key, json.dumps(value)) for key, value in metadata.items()],
        )
