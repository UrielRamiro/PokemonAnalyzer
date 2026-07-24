from __future__ import annotations

from pathlib import Path

from pokebrain.data.repositories import (
    SQLiteAbilityRepository,
    SQLiteItemRepository,
    SQLiteMoveRepository,
    SQLiteSpeciesRepository,
)


class DataManager:
    def __init__(self, database_path: Path | str = "data/database/pokemon.db") -> None:
        self.database_path = Path(database_path)
        self.species = SQLiteSpeciesRepository(self.database_path)
        self.moves = SQLiteMoveRepository(self.database_path)
        self.abilities = SQLiteAbilityRepository(self.database_path)
        self.items = SQLiteItemRepository(self.database_path)

