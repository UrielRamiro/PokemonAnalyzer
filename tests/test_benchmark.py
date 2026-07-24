from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.benchmark.models import BattleBenchmarkResult, BattlePair, BenchmarkConfig
from pokebrain.benchmark.report import build_benchmark_report, calculate_win_rate
from pokebrain.benchmark.repository import BenchmarkResultRepository
from pokebrain.benchmark.runner import _paired_agents, _paired_teams
from pokebrain.benchmark.seed import create_battle_seed
from pokebrain.benchmark.team_sampler import SampledTeam
from pokebrain.benchmark.comparison import compare_benchmark_runs


class BenchmarkTest(unittest.TestCase):
    def test_adjusted_win_rate_counts_tie_as_half_win(self) -> None:
        self.assertEqual(calculate_win_rate(wins=1, losses=1, ties=2), 0.5)

    def test_report_counts_primary_agent_when_sides_are_swapped(self) -> None:
        results = [
            self._result("b1", agent_a="pokebrain-v1", agent_b="max-damage", winner="PokeBrain"),
            self._result("b2", agent_a="max-damage", agent_b="pokebrain-v1", winner="Opponent"),
            self._result("b3", agent_a="pokebrain-v1", agent_b="max-damage", winner="Opponent"),
            self._result("b4", agent_a="max-damage", agent_b="pokebrain-v1", winner=None, reason="tie"),
        ]

        report = build_benchmark_report("run-1", results, primary_agent="pokebrain-v1")

        self.assertEqual(report.wins, 2)
        self.assertEqual(report.losses, 1)
        self.assertEqual(report.ties, 1)
        self.assertEqual(report.adjusted_win_rate, 0.625)

    def test_report_groups_by_opponent_species_and_archetype(self) -> None:
        results = [
            self._result(
                "b1",
                winner="PokeBrain",
                species_b=("dragapult", "kingambit"),
                archetype_b="hyper-offense",
            ),
            self._result(
                "b2",
                winner="Opponent",
                species_b=("dragapult", "greattusk"),
                archetype_b="hyper-offense",
            ),
        ]

        report = build_benchmark_report("run-1", results, primary_agent="pokebrain-v1")

        dragapult = next(row for row in report.opponent_species_rows if row.species_id == "dragapult")
        offense = next(row for row in report.archetype_rows if row.archetype == "hyper-offense")
        self.assertEqual(dragapult.battles, 2)
        self.assertEqual(offense.adjusted_win_rate, 0.5)

    def test_seed_generation_is_reproducible(self) -> None:
        self.assertEqual(create_battle_seed(123, 4), create_battle_seed(123, 4))
        self.assertNotEqual(create_battle_seed(123, 4), create_battle_seed(123, 5))

    def test_pairing_swaps_teams_and_agents(self) -> None:
        team_a = SampledTeam("a", Path("a.txt"))
        team_b = SampledTeam("b", Path("b.txt"))

        self.assertEqual(_paired_teams(team_a, team_b, 0), (team_a, team_b))
        self.assertEqual(_paired_teams(team_a, team_b, 1), (team_b, team_a))
        self.assertEqual(_paired_agents("pokebrain-v1", "max-damage", 0), ("pokebrain-v1", "max-damage"))
        self.assertEqual(_paired_agents("pokebrain-v1", "max-damage", 2), ("max-damage", "pokebrain-v1"))

    def test_repository_saves_run_and_battle(self) -> None:
        tmpdir = ROOT_DIR / ".tmp_tests"
        tmpdir.mkdir(exist_ok=True)
        database = tmpdir / "benchmark-test.db"
        if database.exists():
            database.unlink()
        repository = BenchmarkResultRepository(database)
        config = BenchmarkConfig(
            format_id="gen9ou",
            battle_count=1,
            agent_a_name="pokebrain-v1",
            agent_b_name="random",
            team_pool_path="teams",
            base_seed=1,
        )
        repository.create_run("run-1", "2026-07-19T00:00:00+00:00", config)
        repository.save_pair(
            "run-1",
            BattlePair(
                pair_id="pair-1",
                team_1_id="team-a",
                team_2_id="team-b",
                seed=(1, 2, 3, 4),
            ),
        )
        repository.save_battle("run-1", self._result("battle-1"))

        with sqlite3.connect(database) as connection:
            run_count = connection.execute("SELECT COUNT(*) FROM benchmark_runs").fetchone()[0]
            pair_count = connection.execute("SELECT COUNT(*) FROM benchmark_pairs").fetchone()[0]
            battle_count = connection.execute("SELECT COUNT(*) FROM benchmark_battles").fetchone()[0]

        self.assertEqual(run_count, 1)
        self.assertEqual(pair_count, 1)
        self.assertEqual(battle_count, 1)

    def test_compare_benchmark_runs(self) -> None:
        tmpdir = ROOT_DIR / ".tmp_tests"
        tmpdir.mkdir(exist_ok=True)
        database = tmpdir / "benchmark-compare-test.db"
        if database.exists():
            database.unlink()
        repository = BenchmarkResultRepository(database)
        config = BenchmarkConfig(
            format_id="gen9ou",
            battle_count=1,
            agent_a_name="pokebrain-v1",
            agent_b_name="random",
            team_pool_path="teams",
            base_seed=1,
        )
        repository.create_run("run-a", "2026-07-19T00:00:00+00:00", config)
        repository.create_run("run-b", "2026-07-19T00:00:00+00:00", config)
        repository.save_battle("run-a", self._result("a1", winner="PokeBrain"))
        repository.save_battle("run-b", self._result("b1", winner="Opponent"))

        comparison = compare_benchmark_runs(repository, "run-a", "run-b")

        self.assertEqual(comparison.run_a_adjusted_win_rate, 1.0)
        self.assertEqual(comparison.run_b_adjusted_win_rate, 0.0)
        self.assertTrue(comparison.likely_meaningful)

    def _result(
        self,
        battle_id: str,
        agent_a: str = "pokebrain-v1",
        agent_b: str = "random",
        winner: str | None = "PokeBrain",
        reason: str = "win",
        species_b: tuple[str, ...] = ("mew",),
        archetype_b: str | None = "balance",
    ) -> BattleBenchmarkResult:
        return BattleBenchmarkResult(
            battle_id=battle_id,
            pair_id="pair-1",
            seed=(1, 2, 3, 4),
            agent_a=agent_a,
            agent_b=agent_b,
            team_a_id="team-a",
            team_b_id="team-b",
            winner=winner,
            turns=10,
            illegal_action_count_a=0,
            illegal_action_count_b=0,
            decision_error_count_a=0,
            decision_error_count_b=0,
            duration_seconds=1.0,
            termination_reason=reason,
            run_dir="runs/x",
            average_decision_time_ms=12.0,
            lead_a_id="pikachu",
            lead_b_id=species_b[0] if species_b else None,
            species_a=("pikachu",),
            species_b=species_b,
            archetype_a="balance",
            archetype_b=archetype_b,
        )


if __name__ == "__main__":
    unittest.main()
