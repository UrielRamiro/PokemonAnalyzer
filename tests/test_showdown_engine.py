from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.showdown import ShowdownEngine


class ShowdownEngineTest(unittest.TestCase):
    def test_resolves_species_differently_by_generation(self) -> None:
        engine = ShowdownEngine(ROOT_DIR)

        gen3_charizard = engine.resolve("gen3", "species", "charizard")
        gen9_charizard = engine.resolve("gen9", "species", "charizard")

        self.assertEqual(gen3_charizard["abilities"], {"0": "Blaze"})
        self.assertEqual(gen9_charizard["abilities"]["H"], "Solar Power")

    def test_accepts_valid_team(self) -> None:
        engine = ShowdownEngine(ROOT_DIR)
        team = """
Garchomp @ Rocky Helmet
Ability: Rough Skin
EVs: 252 HP / 4 Def / 252 Spe
Jolly Nature
- Stealth Rock
- Earthquake
- Dragon Tail
- Spikes
"""

        result = engine.validate_team("gen9ou", team)

        self.assertTrue(result.valid)
        self.assertEqual(result.problems, ())

    def test_rejects_banned_pokemon(self) -> None:
        engine = ShowdownEngine(ROOT_DIR)
        team = """
Miraidon @ Choice Specs
Ability: Hadron Engine
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Electro Drift
- Draco Meteor
- Volt Switch
- Overheat
"""

        result = engine.validate_team("gen9ou", team)

        self.assertFalse(result.valid)
        self.assertTrue(result.problems)
        self.assertTrue(any("Miraidon" in problem for problem in result.problems))

    def test_rejects_illegal_move(self) -> None:
        engine = ShowdownEngine(ROOT_DIR)
        team = """
Charizard @ Heavy-Duty Boots
Ability: Blaze
Tera Type: Fire
EVs: 252 SpA / 4 SpD / 252 Spe
Timid Nature
- Flamethrower
- Air Slash
- Roost
- Focus Blast
"""

        result = engine.validate_team("gen9ou", team)

        self.assertFalse(result.valid)
        self.assertTrue(any("Roost" in problem for problem in result.problems))

    def test_lists_formats(self) -> None:
        engine = ShowdownEngine(ROOT_DIR)

        formats = engine.list_formats()
        gen9ou = next(format_data for format_data in formats if format_data["id"] == "gen9ou")

        self.assertEqual(gen9ou["name"], "[Gen 9] OU")
        self.assertEqual(gen9ou["generation"], 9)
        self.assertEqual(gen9ou["game_type"], "singles")
        self.assertIn("Standard", gen9ou["ruleset"])
        self.assertIn("Uber", gen9ou["banlist"])


if __name__ == "__main__":
    unittest.main()
