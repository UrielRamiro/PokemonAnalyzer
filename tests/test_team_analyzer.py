from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.analysis.hazards import HazardAnalyzer
from pokebrain.analysis.removal import RemovalAnalyzer
from pokebrain.analysis.speed_control import SpeedControlAnalyzer
from pokebrain.analysis.type_profile import TypeProfileAnalyzer
from pokebrain.data import DataManager
from pokebrain.team.models import EVSpread, PokemonSet, Team
from pokebrain.team.parser import TeamParser


class TeamAnalyzerTest(unittest.TestCase):
    def test_parser_canonicalizes_showdown_export(self) -> None:
        parsed = TeamParser().parse(
            "gen9ou",
            """
Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
Tera Type: Water
EVs: 252 HP / 4 Def / 252 Spe
Jolly Nature
- Headlong Rush
- Rapid Spin
- Knock Off
- Ice Spinner
""",
        )

        self.assertEqual(parsed.parse_errors, ())
        self.assertIsNotNone(parsed.team)
        member = parsed.team.members[0]
        self.assertEqual(member.species_id, "greattusk")
        self.assertEqual(member.item_id, "heavydutyboots")
        self.assertEqual(member.ability_id, "protosynthesis")
        self.assertIn("rapidspin", member.moves)
        self.assertEqual(member.evs.hp, 252)

    def test_detects_stealth_rock(self) -> None:
        team = Team("gen9ou", (self._set("garchomp", moves=("stealthrock",)),))

        analysis = HazardAnalyzer().analyze(team)

        self.assertEqual(analysis.stealth_rock_users, ("garchomp",))

    def test_detects_rapid_spin(self) -> None:
        team = Team("gen9ou", (self._set("greattusk", moves=("rapidspin",)),))

        analysis = RemovalAnalyzer().analyze(team)

        self.assertEqual(analysis.removers[0].move_id, "rapidspin")

    def test_levitate_grants_ground_immunity(self) -> None:
        team = Team("gen9ou", (self._set("rotomwash", ability_id="levitate"),))

        analysis = TypeProfileAnalyzer(DataManager()).analyze(team)
        rotom = analysis.members[0]
        ground = next(matchup for matchup in rotom.matchups if matchup.attacking_type == "Ground")

        self.assertEqual(ground.multiplier, 0.0)

    def test_garchomp_is_four_times_weak_to_ice(self) -> None:
        team = Team("gen9ou", (self._set("garchomp"),))

        analysis = TypeProfileAnalyzer(DataManager()).analyze(team)
        garchomp = analysis.members[0]
        ice = next(matchup for matchup in garchomp.matchups if matchup.attacking_type == "Ice")

        self.assertEqual(ice.multiplier, 4.0)

    def test_calculates_speed_and_priority(self) -> None:
        team = Team(
            "gen9ou",
            (
                self._set(
                    "kingambit",
                    moves=("suckerpunch",),
                    evs=EVSpread(attack=252),
                    nature="Adamant",
                ),
                self._set(
                    "dragapult",
                    evs=EVSpread(special_attack=252, speed=252),
                    nature="Timid",
                ),
            ),
        )

        analysis = SpeedControlAnalyzer(DataManager()).analyze(team)

        self.assertEqual(analysis.entries[0].species_id, "dragapult")
        self.assertTrue(any(item.move_id == "suckerpunch" for item in analysis.priority))

    def _set(
        self,
        species_id: str,
        moves: tuple[str, ...] = (),
        ability_id: str | None = None,
        item_id: str | None = None,
        evs: EVSpread | None = None,
        nature: str | None = None,
    ) -> PokemonSet:
        return PokemonSet(
            species_id=species_id,
            nickname=None,
            item_id=item_id,
            ability_id=ability_id,
            level=100,
            nature=nature,
            tera_type=None,
            moves=moves,
            evs=evs or EVSpread(),
        )


if __name__ == "__main__":
    unittest.main()

