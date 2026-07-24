from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.analysis.stats import StatCalculator
from pokebrain.damage.models import DamagePokemon
from pokebrain.data.models import BaseStats, PokemonSpecies
from pokebrain.team.parser import TeamParser


CHAMPIONS_TEAM = """
Charizard Mega Y @ Charizardite Y
Ability: Drought
EVs: 20 HP / 32 Def / 1 SpA / 13 Spe
Timid Nature
- Heat Wave
- Solar Beam
- Weather Ball
- Protect

Sylveon @ Fairy Feather
Ability: Pixilate
EVs: 9 HP / 22 Def / 30 SpA / 5 Spe
Modest Nature
- Detect
- Hyper Voice
- Yawn
- Quick Attack

Kingambit @ Chople Berry
Ability: Defiant
EVs: 32 HP / 32 Atk / 2 SpD
Adamant Nature
- Sucker Punch
- Kowtow Cleave
- Low Kick
- Iron Head

Basculegion-M @ Focus Sash
Ability: Adaptability
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Protect
- Last Respects
- Aqua Jet
- Liquidation

Garchomp @ Sitrus Berry
Ability: Rough Skin
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Rock Tomb
- Earthquake
- Dragon Claw
- Protect

Aerodactyl Mega @ Aerodactylite
Ability: Tough Claws
EVs: 22 HP / 12 Atk / 32 Spe
Jolly Nature
- Tailwind
- Dual Wingbeat
- Rock Slide
- Wide Guard
"""


class TeamParserTest(unittest.TestCase):
    def test_parses_evs_and_ivs(self) -> None:
        result = TeamParser().parse(
            "gen9ou",
            """
Flutter Mane @ Booster Energy
Ability: Protosynthesis
Level: 50
Tera Type: Fairy
EVs: 4 HP / 252 SpA / 252 Spe
IVs: 0 Atk / 0 Spe
Timid Nature
- Moonblast
- Shadow Ball
""",
        )

        self.assertFalse(result.parse_errors)
        assert result.team is not None
        flutter = result.team.members[0]
        self.assertEqual(flutter.evs.hp, 4)
        self.assertEqual(flutter.evs.special_attack, 252)
        self.assertEqual(flutter.ivs.attack, 0)
        self.assertEqual(flutter.ivs.speed, 0)
        self.assertEqual(flutter.ivs.hp, 31)

    def test_default_ivs_are_31(self) -> None:
        result = TeamParser().parse(
            "gen9ou",
            """
Garchomp @ Rocky Helmet
Ability: Rough Skin
EVs: 252 HP
Jolly Nature
- Earthquake
""",
        )

        assert result.team is not None
        garchomp = result.team.members[0]
        self.assertEqual(garchomp.ivs.hp, 31)
        self.assertEqual(garchomp.ivs.attack, 31)
        self.assertEqual(garchomp.ivs.speed, 31)

    def test_damage_pokemon_preserves_team_set_ivs(self) -> None:
        result = TeamParser().parse(
            "gen9ou",
            """
Amoonguss @ Sitrus Berry
Ability: Regenerator
Level: 50
EVs: 252 HP / 156 Def / 100 SpD
IVs: 0 Atk / 0 Spe
Relaxed Nature
- Spore
""",
        )

        assert result.team is not None
        damage_pokemon = DamagePokemon.from_team_set(result.team.members[0])

        self.assertEqual(damage_pokemon.level, 50)
        self.assertEqual(damage_pokemon.evs["hp"], 252)
        self.assertEqual(damage_pokemon.ivs["atk"], 0)
        self.assertEqual(damage_pokemon.ivs["spe"], 0)
        self.assertEqual(damage_pokemon.ivs["spa"], 31)

    def test_champions_parses_stat_points_and_rejects_custom_ivs(self) -> None:
        result = TeamParser().parse(
            "gen9championsvgc2026regmb",
            """
Sylveon @ Fairy Feather
Ability: Pixilate
EVs: 9 HP / 22 Def / 30 SpA / 5 Spe
Modest Nature
- Detect
- Hyper Voice
- Yawn
- Quick Attack
""",
        )

        self.assertFalse(result.parse_errors)
        assert result.team is not None
        sylveon = result.team.members[0]
        self.assertEqual(sylveon.evs.hp, 9)
        self.assertEqual(sylveon.evs.defense, 22)
        self.assertEqual(sylveon.evs.special_attack, 30)
        self.assertEqual(sylveon.ivs.speed, 31)

        invalid = TeamParser().parse(
            "gen9championsvgc2026regmb",
            """
Amoonguss @ Sitrus Berry
Ability: Regenerator
EVs: 32 HP / 32 Def / 2 SpD
IVs: 0 Spe
Relaxed Nature
- Spore
""",
        )
        self.assertIn("custom IVs are not legal", invalid.parse_errors[0])

    def test_champions_rejects_stat_points_over_caps(self) -> None:
        result = TeamParser().parse(
            "gen9championsvgc2026regmb",
            """
Kingambit @ Chople Berry
Ability: Defiant
EVs: 33 HP / 32 Atk / 2 SpD
Adamant Nature
- Sucker Punch
""",
        )

        self.assertIn("at most 32 per stat", result.parse_errors[0])

    def test_champions_stat_points_use_direct_formula(self) -> None:
        species = PokemonSpecies(
            id="garchomp",
            name="Garchomp",
            national_dex_number=445,
            generation=4,
            types=("Dragon", "Ground"),
            base_stats=BaseStats(108, 130, 95, 80, 85, 102),
            abilities={},
            height_m=1.9,
            weight_kg=95.0,
        )
        result = TeamParser().parse(
            "gen9championsvgc2026regmb",
            """
Garchomp @ Sitrus Berry
Ability: Rough Skin
Level: 50
EVs: 2 HP / 32 Atk / 32 Spe
Jolly Nature
- Rock Tomb
""",
        )

        assert result.team is not None
        stats = StatCalculator().calculate(result.team.members[0], species, result.team.format_id)

        self.assertEqual(stats.hp, 184)
        self.assertEqual(stats.speed, 151)

    def test_parses_user_champions_team(self) -> None:
        result = TeamParser().parse("gen9championsvgc2026regmb", CHAMPIONS_TEAM)

        self.assertFalse(result.parse_errors)
        assert result.team is not None
        self.assertEqual(len(result.team.members), 6)
        self.assertEqual(result.team.members[0].species_id, "charizardmegay")
        self.assertEqual(result.team.members[-1].species_id, "aerodactylmega")
        self.assertTrue(all(member.ivs.speed == 31 for member in result.team.members))


if __name__ == "__main__":
    unittest.main()
