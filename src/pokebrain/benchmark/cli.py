from __future__ import annotations

from pathlib import Path

from pokebrain.benchmark import (
    BenchmarkConfig,
    BenchmarkResultRepository,
    BenchmarkRunner,
    LocalShowdownBattleRunner,
    TeamSampler,
)
from pokebrain.benchmark.renderer import TextBenchmarkRenderer
from pokebrain.benchmark.comparison import TextBenchmarkComparisonRenderer, compare_benchmark_runs
from pokebrain.benchmark.performance import PerformanceBenchmarkRunner, TextSearchPerformanceRenderer


def run_benchmark_command(
    *,
    format_id: str,
    agent_a: str,
    agent_b: str,
    battles: int,
    teams: Path,
    seed: int,
    maximum_turns: int,
    timeout_seconds: int,
    parallel_workers: int,
    database_path: Path,
) -> None:
    config = BenchmarkConfig(
        format_id=format_id,
        battle_count=battles,
        agent_a_name=agent_a,
        agent_b_name=agent_b,
        team_pool_path=str(teams),
        base_seed=seed,
        parallel_workers=parallel_workers,
        maximum_turns=maximum_turns,
        timeout_seconds=timeout_seconds,
    )
    runner = BenchmarkRunner(
        battle_runner=LocalShowdownBattleRunner(Path(".")),
        team_sampler=TeamSampler(teams),
        result_repository=BenchmarkResultRepository(database_path),
    )
    report = runner.run(config)
    print(TextBenchmarkRenderer().render(config, report))


def compare_benchmark_command(*, run_a: str, run_b: str, database_path: Path) -> None:
    repository = BenchmarkResultRepository(database_path)
    comparison = compare_benchmark_runs(repository, run_a, run_b)
    print(TextBenchmarkComparisonRenderer().render(comparison))


def run_performance_benchmark_command(
    *,
    format_id: str,
    agents: tuple[str, ...],
    pairs: int,
    teams: Path,
    seed: int,
    maximum_turns: int,
    timeout_seconds: int,
    parallel_workers: int,
    database_path: Path,
) -> None:
    benchmark_runner = BenchmarkRunner(
        battle_runner=LocalShowdownBattleRunner(Path(".")),
        team_sampler=TeamSampler(teams),
        result_repository=BenchmarkResultRepository(database_path),
    )
    runs = PerformanceBenchmarkRunner(benchmark_runner).run_pairwise(
        format_id=format_id,
        agents=agents,
        pairs=pairs,
        teams=teams,
        seed=seed,
        maximum_turns=maximum_turns,
        timeout_seconds=timeout_seconds,
        parallel_workers=parallel_workers,
    )
    print(TextSearchPerformanceRenderer().render(runs))
