from __future__ import annotations

import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS species (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    national_dex_number INTEGER NOT NULL,
    generation INTEGER NOT NULL,
    height_m REAL NOT NULL,
    weight_kg REAL NOT NULL,
    base_species TEXT,
    forme TEXT
);

CREATE TABLE IF NOT EXISTS species_types (
    species_id TEXT NOT NULL,
    slot INTEGER NOT NULL,
    type_id TEXT NOT NULL,
    PRIMARY KEY (species_id, slot),
    FOREIGN KEY (species_id) REFERENCES species(id)
);

CREATE TABLE IF NOT EXISTS species_abilities (
    species_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    ability_id TEXT NOT NULL,
    PRIMARY KEY (species_id, slot),
    FOREIGN KEY (species_id) REFERENCES species(id)
);

CREATE TABLE IF NOT EXISTS base_stats (
    species_id TEXT PRIMARY KEY,
    hp INTEGER NOT NULL,
    attack INTEGER NOT NULL,
    defense INTEGER NOT NULL,
    special_attack INTEGER NOT NULL,
    special_defense INTEGER NOT NULL,
    speed INTEGER NOT NULL,
    FOREIGN KEY (species_id) REFERENCES species(id)
);

CREATE TABLE IF NOT EXISTS moves (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type_id TEXT NOT NULL,
    category TEXT NOT NULL,
    power INTEGER,
    accuracy INTEGER,
    pp INTEGER NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS abilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learnsets (
    species_id TEXT NOT NULL,
    move_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    PRIMARY KEY (species_id, move_id, generation),
    FOREIGN KEY (species_id) REFERENCES species(id),
    FOREIGN KEY (move_id) REFERENCES moves(id)
);

CREATE TABLE IF NOT EXISTS formats (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    generation INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS format_rules (
    format_id TEXT NOT NULL,
    slot INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    PRIMARY KEY (format_id, slot),
    FOREIGN KEY (format_id) REFERENCES formats(id)
);

CREATE TABLE IF NOT EXISTS aliases (
    alias TEXT PRIMARY KEY,
    target_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


TABLES = (
    "species_types",
    "species_abilities",
    "base_stats",
    "learnsets",
    "format_rules",
    "species",
    "moves",
    "abilities",
    "items",
    "types",
    "formats",
    "aliases",
    "metadata",
)


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    _ensure_column(connection, "moves", "priority", "INTEGER NOT NULL DEFAULT 0")


def clear_database(connection: sqlite3.Connection) -> None:
    for table in TABLES:
        connection.execute(f"DELETE FROM {table}")


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
