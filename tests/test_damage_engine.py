from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.damage import CachedDamageEngine, DamagePokemon, DamageRequest, DamageResult, FieldState, ShowdownDamageEngine
from pokebrain.damage.cache import build_cache_key
from pokebrain.team.parser import TeamParser


class DamageEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ShowdownDamageEngine(root_dir=ROOT_DIR)

    def test_returns_damage_rolls(self) -> None:
        result = self.engine.calculate(
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(
                    species="Great Tusk",
                    ability="Protosynthesis",
                    item="Choice Band",
                    nature="Adamant",
                    evs={"atk": 252},
                ),
                defender=DamagePokemon(
                    species="Kingambit",
                    ability="Supreme Overlord",
                    nature="Adamant",
                    evs={"hp": 252},
                ),
                move_id="Headlong Rush",
            )
        )

        self.assertTrue(result.damage_rolls)
        self.assertGreater(result.minimum_damage, 0)
        self.assertGreaterEqual(result.maximum_damage, result.minimum_damage)

    def test_ground_move_does_not_damage_levitate_user(self) -> None:
        result = self.engine.calculate(
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(species="Garchomp", evs={"atk": 252}),
                defender=DamagePokemon(species="Rotom-Wash", ability="Levitate"),
                move_id="Earthquake",
            )
        )

        self.assertEqual(result.maximum_damage, 0)

    def test_stab_increases_damage(self) -> None:
        with_stab = self.engine.calculate(
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(species="Charizard", nature="Modest", evs={"spa": 252}),
                defender=DamagePokemon(species="Mew"),
                move_id="Flamethrower",
            )
        )
        without_stab = self.engine.calculate(
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(species="Mew", nature="Modest", evs={"spa": 252}),
                defender=DamagePokemon(species="Mew"),
                move_id="Flamethrower",
            )
        )

        self.assertGreater(with_stab.maximum_damage, without_stab.maximum_damage)

    def test_generation_changes_damage_mechanics(self) -> None:
        gen5 = self.engine.calculate(
            DamageRequest(
                generation=5,
                attacker=DamagePokemon(species="Weavile", nature="Adamant", evs={"atk": 252}),
                defender=DamagePokemon(species="Alakazam"),
                move_id="Knock Off",
            )
        )
        gen9 = self.engine.calculate(
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(species="Weavile", nature="Adamant", evs={"atk": 252}),
                defender=DamagePokemon(species="Alakazam"),
                move_id="Knock Off",
            )
        )

        self.assertNotEqual(gen5.damage_rolls, gen9.damage_rolls)

    def test_calculation_is_deterministic(self) -> None:
        request = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp", nature="Jolly", evs={"atk": 252}),
            defender=DamagePokemon(species="Heatran", evs={"hp": 252}),
            move_id="Earthquake",
            field=FieldState(),
        )

        first = self.engine.calculate(request)
        second = self.engine.calculate(request)

        self.assertEqual(first, second)

    def test_cached_result_matches_uncached_result(self) -> None:
        request = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Great Tusk", ability="Protosynthesis", item="Choice Band", nature="Adamant", evs={"atk": 252}),
            defender=DamagePokemon(species="Kingambit", ability="Supreme Overlord", nature="Adamant", evs={"hp": 252}),
            move_id="Headlong Rush",
        )

        uncached = self.engine.calculate(request)
        cached = CachedDamageEngine(ShowdownDamageEngine(root_dir=ROOT_DIR)).calculate(request)

        self.assertEqual(cached, uncached)

    def test_accepts_sets_from_team_parser(self) -> None:
        attacker_team = TeamParser().parse(
            "gen9ou",
            """
Great Tusk @ Choice Band
Ability: Protosynthesis
EVs: 252 Atk
Adamant Nature
- Headlong Rush
""",
        ).team
        defender_team = TeamParser().parse(
            "gen9ou",
            """
Kingambit
Ability: Supreme Overlord
EVs: 252 HP
Adamant Nature
- Sucker Punch
""",
        ).team

        result = self.engine.calculate(
            DamageRequest(
                generation=9,
                attacker=attacker_team.members[0],
                defender=defender_team.members[0],
                move_id=attacker_team.members[0].moves[0],
            )
        )

        self.assertGreater(result.maximum_damage, 0)

    def test_calculate_many_preserves_request_order(self) -> None:
        requests = (
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(species="Garchomp", evs={"atk": 252}),
                defender=DamagePokemon(species="Heatran"),
                move_id="Earthquake",
            ),
            DamageRequest(
                generation=9,
                attacker=DamagePokemon(species="Charizard", evs={"spa": 252}),
                defender=DamagePokemon(species="Mew"),
                move_id="Flamethrower",
            ),
        )

        results = self.engine.calculate_many(requests)

        self.assertEqual(tuple(result.move_id for result in results), ("Earthquake", "Flamethrower"))
        self.assertGreater(results[0].maximum_damage, results[1].maximum_damage)

    def test_duplicate_requests_are_calculated_once(self) -> None:
        inner = FakeBatchDamageEngine()
        engine = CachedDamageEngine(inner)
        request = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp", evs={"atk": 252}),
            defender=DamagePokemon(species="Heatran"),
            move_id="Earthquake",
        )

        results = engine.calculate_many((request, request))

        self.assertEqual(len(results), 2)
        self.assertEqual(inner.batch_calls, 1)
        self.assertEqual(inner.batch_sizes, [1])
        self.assertEqual(engine.metrics.requested_calculations, 2)
        self.assertEqual(engine.metrics.unique_calculations, 1)

    def test_l1_cache_tracks_cross_scenario_hits(self) -> None:
        inner = FakeBatchDamageEngine()
        engine = CachedDamageEngine(inner)
        request = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp", evs={"atk": 252}),
            defender=DamagePokemon(species="Heatran"),
            move_id="Earthquake",
        )

        engine.begin_search_scope()
        engine.set_scenario_id("scenario-1")
        engine.calculate(request)
        engine.set_scenario_id("scenario-2")
        engine.calculate(request)

        self.assertEqual(engine.metrics.l1_cache_hits, 1)
        self.assertEqual(engine.metrics.cross_scenario_hits, 1)
        self.assertEqual(engine.metrics.same_scenario_hits, 0)
        self.assertEqual(inner.batch_calls, 1)

    def test_item_change_creates_different_cache_key(self) -> None:
        base = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp", item="Life Orb"),
            defender=DamagePokemon(species="Heatran"),
            move_id="Earthquake",
        )
        changed = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp", item="Choice Band"),
            defender=DamagePokemon(species="Heatran"),
            move_id="Earthquake",
        )

        self.assertNotEqual(build_cache_key(base), build_cache_key(changed))

    def test_weather_change_creates_different_cache_key(self) -> None:
        clear = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Charizard"),
            defender=DamagePokemon(species="Mew"),
            move_id="Flamethrower",
        )
        sun = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Charizard"),
            defender=DamagePokemon(species="Mew"),
            move_id="Flamethrower",
            field=FieldState(weather="Sun"),
        )

        self.assertNotEqual(build_cache_key(clear), build_cache_key(sun))

    def test_current_hp_does_not_invalidate_raw_damage_key(self) -> None:
        full_hp = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp"),
            defender=DamagePokemon(species="Heatran", current_hp=300),
            move_id="Earthquake",
        )
        damaged = DamageRequest(
            generation=9,
            attacker=DamagePokemon(species="Garchomp"),
            defender=DamagePokemon(species="Heatran", current_hp=100),
            move_id="Earthquake",
        )

        self.assertEqual(build_cache_key(full_hp), build_cache_key(damaged))


class FakeBatchDamageEngine:
    def __init__(self) -> None:
        self.batch_calls = 0
        self.batch_sizes: list[int] = []

    def calculate(self, request: DamageRequest) -> DamageResult:
        return self.calculate_many((request,))[0]

    def calculate_many(self, requests: tuple[DamageRequest, ...]) -> tuple[DamageResult, ...]:
        self.batch_calls += 1
        self.batch_sizes.append(len(requests))
        return tuple(
            DamageResult(
                generation=request.generation,
                attacker_id="attacker",
                defender_id="defender",
                move_id=request.move_id,
                damage_rolls=(10,),
                minimum_damage=10,
                maximum_damage=10,
                defender_max_hp=100,
                minimum_percent=10.0,
                maximum_percent=10.0,
                description="fake",
                ohko_chance=0.0,
                classification="chip",
            )
            for request in requests
        )


if __name__ == "__main__":
    unittest.main()
