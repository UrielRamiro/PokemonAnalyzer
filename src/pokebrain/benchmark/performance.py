from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from pokebrain.benchmark.models import BenchmarkConfig, BenchmarkReport, SearchPerformanceReport
from pokebrain.benchmark.runner import BenchmarkRunner


def build_search_performance_report(
    benchmark: BenchmarkReport,
    agent_name: str,
) -> SearchPerformanceReport:
    decision_times: list[float] = []
    nodes: list[float] = []
    depths: list[float] = []
    layered_completed_depths: list[float] = []
    layered_attempted_depths: list[float] = []
    belief_scenarios: list[float] = []
    policy_actions_expanded: list[float] = []
    damage_requests = 0
    unique_damage_requests = 0
    l1_cache_hits = 0
    same_scenario_hits = 0
    cross_scenario_hits = 0
    l2_cache_hits = 0
    bridge_batches = 0
    bridge_requests = 0
    bridge_time_ms = 0.0
    fallback_count = 0
    layered_incomplete_layers = 0
    layered_timeout_before_batch = 0
    layered_timeout_after_batch = 0
    layered_batches_by_depth: Counter[str] = Counter()
    layered_requests_by_depth: Counter[str] = Counter()
    interruption_reasons: Counter[str] = Counter()

    battle_count = 0
    illegal_actions = 0
    crashes = 0
    protocol_errors = 0

    for battle in benchmark.battle_results:
        if agent_name not in {battle.agent_a, battle.agent_b}:
            continue
        battle_count += 1
        player_ids = set()
        if battle.agent_a == agent_name:
            player_ids.add("p1")
            illegal_actions += battle.illegal_action_count_a
            crashes += battle.decision_error_count_a
        if battle.agent_b == agent_name:
            player_ids.add("p2")
            illegal_actions += battle.illegal_action_count_b
            crashes += battle.decision_error_count_b
        if battle.termination_reason == "protocol_error":
            protocol_errors += 1

        for entry in _iter_decisions(Path(battle.run_dir)):
            if entry.get("player_id") not in player_ids:
                continue
            selected = entry.get("selected_action") or {}
            if selected.get("type") not in {"move", "switch"}:
                continue
            decision_time = entry.get("decision_time_ms")
            if isinstance(decision_time, (int, float)):
                decision_times.append(float(decision_time))
            metrics = entry.get("metrics") or {}
            if not isinstance(metrics, dict):
                metrics = {}
            if "search_nodes" in metrics:
                nodes.append(float(metrics.get("search_nodes") or 0))
            if "search_depth_reached" in metrics:
                depths.append(float(metrics.get("search_depth_reached") or 0))
            if "layered_completed_depth" in metrics:
                layered_completed_depths.append(float(metrics.get("layered_completed_depth") or 0))
            if "layered_attempted_depth" in metrics:
                layered_attempted_depths.append(float(metrics.get("layered_attempted_depth") or 0))
            if "belief_scenarios" in metrics:
                belief_scenarios.append(float(metrics.get("belief_scenarios") or 0))
            if "policy_actions_expanded" in metrics:
                policy_actions_expanded.append(float(metrics.get("policy_actions_expanded") or 0))
            layered_incomplete_layers += int(metrics.get("layered_incomplete_layers") or 0)
            layered_timeout_before_batch += int(metrics.get("layered_timeout_before_batch") or 0)
            layered_timeout_after_batch += int(metrics.get("layered_timeout_after_batch") or 0)
            _merge_depth_counter(layered_batches_by_depth, metrics.get("layered_batches_by_depth"))
            _merge_depth_counter(layered_requests_by_depth, metrics.get("layered_requests_by_depth"))
            damage_requests += int(metrics.get("damage_requested_calculations") or 0)
            unique_damage_requests += int(metrics.get("damage_unique_calculations") or 0)
            l1_cache_hits += int(metrics.get("damage_l1_cache_hits") or 0)
            same_scenario_hits += int(metrics.get("damage_same_scenario_hits") or 0)
            cross_scenario_hits += int(metrics.get("damage_cross_scenario_hits") or 0)
            l2_cache_hits += int(metrics.get("damage_l2_cache_hits") or 0)
            bridge_batches += int(metrics.get("damage_bridge_batches") or 0)
            bridge_requests += int(metrics.get("damage_bridge_requests") or 0)
            bridge_time_ms += float(metrics.get("damage_total_bridge_time_ms") or 0)
            if metrics.get("search_fallback_used"):
                fallback_count += 1
            if "search_interruption_reason" in metrics:
                reason = str(metrics.get("search_interruption_reason") or "completed")
                interruption_reasons[reason] += 1

    return SearchPerformanceReport(
        agent_name=agent_name,
        battles=battle_count,
        decisions=len(decision_times),
        average_decision_ms=_average(decision_times),
        p50_decision_ms=_percentile(decision_times, 50),
        p95_decision_ms=_percentile(decision_times, 95),
        p99_decision_ms=_percentile(decision_times, 99),
        maximum_decision_ms=max(decision_times, default=0.0),
        average_nodes=_average(nodes),
        average_depth_reached=_average(depths),
        average_layered_completed_depth=_average(layered_completed_depths),
        average_layered_attempted_depth=_average(layered_attempted_depths),
        average_belief_scenarios=_average(belief_scenarios),
        average_policy_actions_expanded=_average(policy_actions_expanded),
        damage_requests=damage_requests,
        unique_damage_requests=unique_damage_requests,
        l1_cache_hits=l1_cache_hits,
        same_scenario_hits=same_scenario_hits,
        cross_scenario_hits=cross_scenario_hits,
        l2_cache_hits=l2_cache_hits,
        bridge_batches=bridge_batches,
        average_bridge_batch_size=bridge_requests / bridge_batches if bridge_batches else 0.0,
        bridge_time_ms=bridge_time_ms,
        fallback_count=fallback_count,
        timeout_count=interruption_reasons["time_limit"],
        layered_incomplete_layers=layered_incomplete_layers,
        layered_timeout_before_batch=layered_timeout_before_batch,
        layered_timeout_after_batch=layered_timeout_after_batch,
        layered_batches_by_depth=tuple(sorted(layered_batches_by_depth.items())),
        layered_requests_by_depth=tuple(sorted(layered_requests_by_depth.items())),
        interruption_reasons=tuple(sorted(interruption_reasons.items())),
        illegal_actions=illegal_actions,
        crashes=crashes,
        protocol_errors=protocol_errors,
    )


def _iter_decisions(run_dir: Path):
    path = run_dir / "decisions.jsonl"
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield json.loads(line)


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * (percentile / 100)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass(frozen=True, slots=True)
class PerformanceBenchmarkRun:
    matchup: str
    benchmark: BenchmarkReport
    performance_reports: tuple[SearchPerformanceReport, ...]


class PerformanceBenchmarkRunner:
    def __init__(self, benchmark_runner: BenchmarkRunner) -> None:
        self._benchmark_runner = benchmark_runner

    def run_pairwise(
        self,
        *,
        format_id: str,
        agents: tuple[str, ...],
        pairs: int,
        teams: Path,
        seed: int,
        maximum_turns: int,
        timeout_seconds: int,
        parallel_workers: int,
    ) -> tuple[PerformanceBenchmarkRun, ...]:
        runs: list[PerformanceBenchmarkRun] = []
        for agent_a, agent_b in combinations(agents, 2):
            config = BenchmarkConfig(
                format_id=format_id,
                battle_count=pairs * 2,
                agent_a_name=agent_a,
                agent_b_name=agent_b,
                team_pool_path=str(teams),
                base_seed=seed,
                parallel_workers=parallel_workers,
                maximum_turns=maximum_turns,
                timeout_seconds=timeout_seconds,
            )
            benchmark = self._benchmark_runner.run(config)
            runs.append(
                PerformanceBenchmarkRun(
                    matchup=f"{agent_a} vs {agent_b}",
                    benchmark=benchmark,
                    performance_reports=(
                        build_search_performance_report(benchmark, agent_a),
                        build_search_performance_report(benchmark, agent_b),
                    ),
                )
            )
        return tuple(runs)


class TextSearchPerformanceRenderer:
    def render(self, runs: tuple[PerformanceBenchmarkRun, ...]) -> str:
        lines: list[str] = ["Benchmark de performance", ""]
        for run in runs:
            lines.append(run.matchup)
            lines.append("-" * len(run.matchup))
            lines.extend(
                [
                    f"Run ID: {run.benchmark.run_id}",
                    f"Partidas: {run.benchmark.total_battles}",
                    f"Taxa ajustada do primeiro agente: {run.benchmark.adjusted_win_rate * 100:.1f}%",
                    f"Acoes ilegais por partida: {run.benchmark.illegal_action_rate:.2f}",
                    f"Falhas do agente: {run.benchmark.crash_rate * 100:.1f}%",
                    f"Erros de protocolo: {run.benchmark.protocol_error_rate * 100:.1f}%",
                    "",
                ]
            )
            for report in run.performance_reports:
                lines.extend(self._render_report(report))
                lines.append("")
        return "\n".join(lines).rstrip()

    def _render_report(self, report: SearchPerformanceReport) -> list[str]:
        return [
            f"Performance: {report.agent_name}",
            f"Battles: {report.battles}",
            f"Decisions: {report.decisions}",
            f"Decision ms: avg {report.average_decision_ms:.1f}, p50 {report.p50_decision_ms:.1f}, p95 {report.p95_decision_ms:.1f}, p99 {report.p99_decision_ms:.1f}, max {report.maximum_decision_ms:.1f}",
            f"Search: avg nodes {report.average_nodes:.1f}, avg depth {report.average_depth_reached:.1f}",
            f"Layered: completed depth {report.average_layered_completed_depth:.1f}, attempted depth {report.average_layered_attempted_depth:.1f}, incomplete layers {report.layered_incomplete_layers}, timeout before/after batch {report.layered_timeout_before_batch}/{report.layered_timeout_after_batch}",
            f"Layered batches: {_format_reasons(report.layered_batches_by_depth)}; requests: {_format_reasons(report.layered_requests_by_depth)}",
            f"Belief: avg scenarios {report.average_belief_scenarios:.1f}",
            f"Policy: avg opponent actions expanded {report.average_policy_actions_expanded:.1f}",
            f"Damage: requested {report.damage_requests}, unique {report.unique_damage_requests}, L1 hits {report.l1_cache_hits}, same-scenario hits {report.same_scenario_hits}, cross-scenario hits {report.cross_scenario_hits}, L2 hits {report.l2_cache_hits}, bridge batches {report.bridge_batches}, avg batch {report.average_bridge_batch_size:.1f}, bridge {report.bridge_time_ms:.1f} ms",
            f"Fallbacks: {report.fallback_count}; timeouts: {report.timeout_count}",
            f"Interruptions: {_format_reasons(report.interruption_reasons)}",
            f"Stability: illegal {report.illegal_actions}, crashes {report.crashes}, protocol errors {report.protocol_errors}",
        ]


def _format_reasons(reasons: tuple[tuple[str, int], ...]) -> str:
    if not reasons:
        return "none"
    return ", ".join(f"{name}={count}" for name, count in reasons)


def _merge_depth_counter(counter: Counter[str], raw) -> None:
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        counter[str(key)] += int(value or 0)
