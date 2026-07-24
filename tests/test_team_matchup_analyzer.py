from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.analysis.team_matchup import TeamMatchupAnalyzer
from pokebrain.analysis.team_matchup.scoring import calculate_coverage_score
from pokebrain.damage.cache import CachedDamageEngine
from pokebrain.damage.models import DamageResult
from pokebrain.team.models import EVSpread, PokemonSet, Team


class FakeDamageEngine:
    def __init__(self) -> None:
        self.calls = 0

    def calculate(self, request):
        self.calls += 1
        return DamageResult(
            generation=request.generation,
            attacker_id="a",
            defender_id="b",
            move_id=request.move_id,
            damage_rolls=(10,),
            minimum_damage=10,
            maximum_damage=10,
            defender_max_hp=100,
            minimum_percent=10,
            maximum_percent=10,
            description="fake",
            ohko_chance=0,
            classification="low_damage",
        )


class TeamMatchupAnalyzerTest(unittest.TestCase):
    def test_builds_every_matrix_cell(self) -> None:
        result = TeamMatchupAnalyzer().compare(
            generation=9,
            team_a=Team("gen9ou", (self._set("greattusk", ("headlongrush",)), self._set("kingambit", ("suckerpunch",)))),
            team_b=Team("gen9ou", (
                self._set("kingambit", ("kowtowcleave",)),
                self._set("dragapult", ("shadowball",)),
                self._set("heatran", ("flashcannon",)),
            )),
        )

        self.assertEqual(len(result.matrix.cells), 6)

    def test_detects_threat_without_favorable_answer(self) -> None:
        result = TeamMatchupAnalyzer().compare(
            generation=9,
            team_a=Team("gen9ou", (self._set("garchomp", ("earthquake",)),)),
            team_b=Team("gen9ou", (self._set("rotomwash", ("hydropump",), ability_id="levitate"),)),
        )

        threat = result.threats_to_team_a[0]

        self.assertIn(threat.severity, {"critical", "high"})

    def test_detects_single_answer_dependency(self) -> None:
        result = TeamMatchupAnalyzer().compare(
            generation=9,
            team_a=Team("gen9ou", (
                self._set("kingambit", ("suckerpunch",)),
                self._set("greattusk", ("rapidspin",)),
            )),
            team_b=Team("gen9ou", (self._set("dragapult", ("shadowball",)),)),
        )

        threat = result.threats_to_team_a[0]

        self.assertEqual(threat.severity, "moderate")

    def test_calculates_member_coverage(self) -> None:
        self.assertEqual(
            calculate_coverage_score(favorable=3, unfavorable=1, even=1, uncertain=1),
            (3 + 0.25 - 1) / 6,
        )

    def test_preserves_uncertain_matchups(self) -> None:
        result = TeamMatchupAnalyzer().compare(
            generation=9,
            team_a=Team("gen9ou", (self._set("blissey", ("softboiled",)),)),
            team_b=Team("gen9ou", (self._set("toxapex", ("recover",)),)),
        )

        self.assertTrue(result.team_a_summaries[0].uncertain_against)

    def test_damage_cache_reuses_results(self) -> None:
        inner = FakeDamageEngine()
        cached = CachedDamageEngine(inner)
        from pokebrain.damage import DamagePokemon, DamageRequest

        request = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Mew"),
            defender=DamagePokemon(species="Mew"),
            move_id="Pound",
        )

        cached.calculate(request)
        cached.calculate(request)

        self.assertEqual(inner.calls, 1)

    def _set(
        self,
        species_id: str,
        moves: tuple[str, ...],
        ability_id: str | None = None,
    ) -> PokemonSet:
        return PokemonSet(
            species_id=species_id,
            nickname=None,
            item_id=None,
            ability_id=ability_id,
            level=100,
            nature=None,
            tera_type=None,
            moves=moves,
            evs=EVSpread(),
        )


if __name__ == "__main__":
    unittest.main()

