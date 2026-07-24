from __future__ import annotations

from dataclasses import dataclass


Seed = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class BenchmarkConfig:
    format_id: str
    battle_count: int
    agent_a_name: str
    agent_b_name: str
    team_pool_path: str
    base_seed: int
    parallel_workers: int = 1
    maximum_turns: int = 500
    timeout_seconds: int = 120


@dataclass(frozen=True, slots=True)
class AgentMetadata:
    version: str
    git_commit: str | None
    configuration_hash: str


@dataclass(frozen=True, slots=True)
class BattlePair:
    pair_id: str
    team_1_id: str
    team_2_id: str
    seed: Seed


@dataclass(frozen=True, slots=True)
class BattleBenchmarkResult:
    battle_id: str
    pair_id: str
    seed: Seed
    agent_a: str
    agent_b: str
    team_a_id: str
    team_b_id: str
    winner: str | None
    turns: int
    illegal_action_count_a: int
    illegal_action_count_b: int
    decision_error_count_a: int
    decision_error_count_b: int
    duration_seconds: float
    termination_reason: str
    run_dir: str
    average_decision_time_ms: float = 0.0
    lead_a_id: str | None = None
    lead_b_id: str | None = None
    species_a: tuple[str, ...] = ()
    species_b: tuple[str, ...] = ()
    archetype_a: str | None = None
    archetype_b: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    run_id: str
    total_battles: int
    wins: int
    losses: int
    ties: int
    win_rate: float
    loss_rate: float
    tie_rate: float
    adjusted_win_rate: float
    confidence_interval_95: tuple[float, float]
    average_turns: float
    median_turns: float
    illegal_action_rate: float
    crash_rate: float
    protocol_error_rate: float
    average_decision_time_ms: float
    matchup_rows: tuple[BenchmarkMatchupRow, ...] = ()
    lead_rows: tuple[BenchmarkLeadRow, ...] = ()
    opponent_species_rows: tuple[BenchmarkSpeciesRow, ...] = ()
    archetype_rows: tuple[BenchmarkArchetypeRow, ...] = ()
    self_play_warning: str | None = None
    battle_results: tuple[BattleBenchmarkResult, ...] = ()


@dataclass(frozen=True, slots=True)
class BenchmarkMatchupRow:
    team_id: str
    battles: int
    wins: int
    losses: int
    ties: int
    adjusted_win_rate: float


@dataclass(frozen=True, slots=True)
class BenchmarkLeadRow:
    lead_id: str
    battles: int
    wins: int
    losses: int
    ties: int
    adjusted_win_rate: float


@dataclass(frozen=True, slots=True)
class BenchmarkSpeciesRow:
    species_id: str
    battles: int
    wins: int
    losses: int
    ties: int
    adjusted_win_rate: float


@dataclass(frozen=True, slots=True)
class BenchmarkArchetypeRow:
    archetype: str
    battles: int
    wins: int
    losses: int
    ties: int
    adjusted_win_rate: float


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    run_a_id: str
    run_b_id: str
    run_a_adjusted_win_rate: float
    run_b_adjusted_win_rate: float
    difference: float
    run_a_confidence_interval_95: tuple[float, float]
    run_b_confidence_interval_95: tuple[float, float]
    likely_meaningful: bool


@dataclass(frozen=True, slots=True)
class SearchPerformanceReport:
    agent_name: str
    battles: int
    decisions: int
    average_decision_ms: float
    p50_decision_ms: float
    p95_decision_ms: float
    p99_decision_ms: float
    maximum_decision_ms: float
    average_nodes: float
    average_depth_reached: float
    average_layered_completed_depth: float
    average_layered_attempted_depth: float
    average_belief_scenarios: float
    average_policy_actions_expanded: float
    damage_requests: int
    unique_damage_requests: int
    l1_cache_hits: int
    same_scenario_hits: int
    cross_scenario_hits: int
    l2_cache_hits: int
    bridge_batches: int
    average_bridge_batch_size: float
    bridge_time_ms: float
    fallback_count: int
    timeout_count: int
    layered_incomplete_layers: int
    layered_timeout_before_batch: int
    layered_timeout_after_batch: int
    layered_batches_by_depth: tuple[tuple[str, int], ...]
    layered_requests_by_depth: tuple[tuple[str, int], ...]
    interruption_reasons: tuple[tuple[str, int], ...]
    illegal_actions: int
    crashes: int
    protocol_errors: int
