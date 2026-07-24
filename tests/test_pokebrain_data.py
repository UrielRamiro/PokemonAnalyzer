from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.data.importer import SQLiteImporter
from pokebrain.data.manager import DataManager

SCRATCH_DIR = Path(".tmp_tests")


class PokebrainDataTest(unittest.TestCase):
    def setUp(self) -> None:
        SCRATCH_DIR.mkdir(exist_ok=True)
        self.snapshot_dir = SCRATCH_DIR / "snapshot_v1"
        self.snapshot_dir.mkdir(exist_ok=True)
        self.database_path = SCRATCH_DIR / "pokebrain.db"
        self.database_path.unlink(missing_ok=True)
        self._write_snapshot()

    def test_charizard_can_be_loaded(self) -> None:
        SQLiteImporter(self.database_path).import_snapshot(self.snapshot_dir)
        data_manager = DataManager(self.database_path)

        charizard = data_manager.species.get_by_id("charizard")

        self.assertIsNotNone(charizard)
        self.assertEqual(charizard.name, "Charizard")
        self.assertEqual(charizard.types, ("Fire", "Flying"))
        self.assertEqual(charizard.base_stats.speed, 100)

    def test_alias_can_resolve_species(self) -> None:
        SQLiteImporter(self.database_path).import_snapshot(self.snapshot_dir)
        data_manager = DataManager(self.database_path)

        charizard = data_manager.species.get_by_id("zard")

        self.assertIsNotNone(charizard)
        self.assertEqual(charizard.id, "charizard")

    def test_importing_same_snapshot_twice_is_idempotent(self) -> None:
        importer = SQLiteImporter(self.database_path)

        importer.import_snapshot(self.snapshot_dir)
        importer.import_snapshot(self.snapshot_dir)
        data_manager = DataManager(self.database_path)

        self.assertEqual(len(data_manager.species.search("charizard")), 1)

    def _write_snapshot(self) -> None:
        self._write("species.json", [
            {
                "id": "charizard",
                "name": "Charizard",
                "national_dex": 6,
                "generation": 1,
                "types": ["Fire", "Flying"],
                "base_stats": {
                    "hp": 78,
                    "atk": 84,
                    "def": 78,
                    "spa": 109,
                    "spd": 85,
                    "spe": 100,
                },
                "abilities": {"0": "Blaze", "H": "Solar Power"},
                "height_m": 1.7,
                "weight_kg": 90.5,
            }
        ])
        self._write("moves.json", [
            {
                "id": "flamethrower",
                "name": "Flamethrower",
                "type": "Fire",
                "category": "Special",
                "power": 90,
                "accuracy": 100,
                "pp": 15,
                "priority": 0,
            }
        ])
        self._write("abilities.json", [
            {"id": "blaze", "name": "Blaze", "description": None},
            {"id": "solarpower", "name": "Solar Power", "description": None},
        ])
        self._write("items.json", [
            {"id": "heavydutyboots", "name": "Heavy-Duty Boots", "description": None}
        ])
        self._write("learnsets.json", [
            {"pokemon_id": "charizard", "move_id": "flamethrower", "generation": 9}
        ])
        self._write("formats.json", [
            {"id": "gen9ou", "name": "Gen 9 OU", "generation": 9, "ruleset": ["Standard"]}
        ])
        self._write("aliases.json", [
            {"alias": "zard", "target_id": "charizard"}
        ])
        self._write("metadata.json", {
            "source": "test",
            "source_commit": "test",
            "imported_at": "2026-07-19T00:00:00Z",
            "schema_version": 1,
            "record_counts": {
                "species": 1,
                "moves": 1,
                "abilities": 2,
                "items": 1,
            },
        })

    def _write(self, filename: str, data) -> None:
        with (self.snapshot_dir / filename).open("w", encoding="utf-8") as file:
            json.dump(data, file)


if __name__ == "__main__":
    unittest.main()
