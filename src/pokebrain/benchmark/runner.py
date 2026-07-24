from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from dataclasses import dataclass

from pokebrain.benchmark.battle_runner import LocalShowdownBattleRunner
from pokebrain.benchmark.models import BattleBenchmarkResult, BattlePair, BenchmarkConfig, BenchmarkReport
from pokebrain.benchmark.report import build_benchmark_report
from pokebrain.benchmark.repository import BenchmarkResultRepository
from pokebrain.benchmark.seed import create_battle_seed
from pokebrain.benchmark.team_sampler import SampledTeam, TeamSampler


class BenchmarkRunner:
    def __init__(
        self,
        battle_runner: LocalShowdownBattleRunner,
        team_sampler: TeamSampler,
        result_repository: BenchmarkResultRepository,
    ) -> None:
        self._battle_runner = battle_runner
        self._team_sampler = team_sampler
        self._result_repository = result_repository

    def run(self, config: BenchmarkConfig) -> BenchmarkReport:
        run_id = f"benchmark-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        self._result_repository.create_run(
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            config=config,
        )
        results: list[BattleBenchmarkResult] = []
        saved_pair_ids: set[str] = set()
        tasks: list[_BattleTask] = []

        for battle_number in range(config.battle_count):
            pair_number = battle_number // 2
            seed = create_battle_seed(config.base_seed, pair_number)
            team_1, team_2 = self._team_sampler.sample_pair(seed)
            pair = BattlePair(
                pair_id=f"{run_id}-pair-{pair_number + 1:05d}",
                team_1_id=team_1.team_id,
                team_2_id=team_2.team_id,
                seed=seed,
            )
            if pair.pair_id not in saved_pair_ids:
                self._result_repository.save_pair(run_id, pair)
                saved_pair_ids.add(pair.pair_id)
            team_a, team_b = _paired_teams(team_1, team_2, battle_number)
            agent_a, agent_b = _paired_agents(config.agent_a_name, config.agent_b_name, battle_number)
            battle_id = f"{run_id}-{battle_number + 1:05d}"
            tasks.append(
                _BattleTask(
                    battle_id=battle_id,
                    pair_id=pair.pair_id,
                    seed=seed,
                    team_a=team_a,
                    team_b=team_b,
                    agent_a=agent_a,
                    agent_b=agent_b,
                )
            )

        if config.parallel_workers <= 1:
            for task in tasks:
                result = self._run_task(config, task)
                self._result_repository.save_battle(run_id, result)
                results.append(result)
        else:
            with ThreadPoolExecutor(max_workers=config.parallel_workers) as executor:
                futures = [executor.submit(self._run_task, config, task) for task in tasks]
                for future in as_completed(futures):
                    result = future.result()
                    self._result_repository.save_battle(run_id, result)
                    results.append(result)

        return build_benchmark_report(run_id, results, primary_agent=config.agent_a_name)

    def _run_task(self, config: BenchmarkConfig, task: "_BattleTask") -> BattleBenchmarkResult:
        return self._battle_runner.run(
            battle_id=task.battle_id,
            pair_id=task.pair_id,
            format_id=config.format_id,
            agent_a_name=task.agent_a,
            agent_b_name=task.agent_b,
            team_a=task.team_a,
            team_b=task.team_b,
            seed=task.seed,
            maximum_turns=config.maximum_turns,
            timeout_seconds=config.timeout_seconds,
        )


def _paired_teams(team_1: SampledTeam, team_2: SampledTeam, battle_number: int) -> tuple[SampledTeam, SampledTeam]:
    if battle_number % 2 == 0:
        return team_1, team_2
    return team_2, team_1


def _paired_agents(agent_a: str, agent_b: str, battle_number: int) -> tuple[str, str]:
    side_pair_index = battle_number // 2
    if side_pair_index % 2 == 0:
        return agent_a, agent_b
    return agent_b, agent_a


@dataclass(frozen=True, slots=True)
class _BattleTask:
    battle_id: str
    pair_id: str
    seed: tuple[int, int, int, int]
    team_a: SampledTeam
    team_b: SampledTeam
    agent_a: str
    agent_b: str
