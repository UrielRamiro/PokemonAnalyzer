from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.analysis.matchup import MatchupAnalyzer, MatchupVerdict, TurnOrder
from pokebrain.analysis.matchup.ko_classifier import calculate_expected_damage
from pokebrain.team.models import EVSpread, PokemonSet


class MatchupAnalyzerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = MatchupAnalyzer()

    def test_faster_pokemon_with_ohko_is_favored(self) -> None:
        result = self.analyzer.compare(
            generation=9,
            pokemon_a=self._set(
                "greattusk",
                item_id="choiceband",
                ability_id="protosynthesis",
                nature="Adamant",
                evs=EVSpread(attack=252, speed=252),
                moves=("headlongrush",),
            ),
            pokemon_b=self._set(
                "kingambit",
                ability_id="supremeoverlord",
                nature="Adamant",
                evs=EVSpread(hp=252),
                moves=("kowtowcleave",),
            ),
        )

        self.assertIs(result.verdict, MatchupVerdict.A_FAVORED)

    def test_priority_can_reverse_turn_order(self) -> None:
        result = self.analyzer.compare(
            generation=9,
            pokemon_a=self._set("dragapult", nature="Timid", evs=EVSpread(speed=252), moves=("shadowball",)),
            pokemon_b=self._set("kingambit", nature="Adamant", evs=EVSpread(attack=252), moves=("suckerpunch",)),
        )

        self.assertIs(result.turn_order, TurnOrder.B_FIRST)

    def test_pokemon_without_damaging_option_is_unfavored(self) -> None:
        result = self.analyzer.compare(
            generation=9,
            pokemon_a=self._set("garchomp", moves=("earthquake",)),
            pokemon_b=self._set("rotomwash", ability_id="levitate", moves=("hydropump",)),
        )

        self.assertTrue(result.pokemon_a.best_move.is_immune)
        self.assertIs(result.verdict, MatchupVerdict.B_FAVORED)

    def test_equal_speed_produces_speed_tie(self) -> None:
        result = self.analyzer.compare(
            generation=9,
            pokemon_a=self._set("mew", moves=("psychic",)),
            pokemon_b=self._set("mew", moves=("psychic",)),
        )

        self.assertIs(result.turn_order, TurnOrder.SPEED_TIE)

    def test_faster_ko_range_is_favored(self) -> None:
        result = self.analyzer.compare(
            generation=9,
            pokemon_a=self._set("garchomp", nature="Jolly", evs=EVSpread(attack=252, speed=252), moves=("earthquake",)),
            pokemon_b=self._set("heatran", evs=EVSpread(hp=252), moves=("flashcannon",)),
        )

        self.assertIs(result.verdict, MatchupVerdict.A_FAVORED)

    def test_accuracy_affects_expected_damage(self) -> None:
        perfect = calculate_expected_damage((100,), 100)
        inaccurate = calculate_expected_damage((120,), 70)

        self.assertEqual(perfect, 100)
        self.assertEqual(inaccurate, 84)

    def _set(
        self,
        species_id: str,
        moves: tuple[str, ...],
        ability_id: str | None = None,
        item_id: str | None = None,
        nature: str | None = None,
        evs: EVSpread | None = None,
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

