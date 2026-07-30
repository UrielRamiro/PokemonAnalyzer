from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from pokebrain.benchmark.metadata import build_agent_metadata
from pokebrain.benchmark.models import BattleBenchmarkResult, BattlePair, BenchmarkConfig
from pokebrain.benchmark.seed import seed_to_text
from pokebrain.benchmark.team_features import text_tuple, tuple_from_text


class BenchmarkResultRepository:
    def __init__(self, database_path: Path | str = "data/database/benchmarks.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_run(self, run_id: str, created_at: str, config: BenchmarkConfig) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO benchmark_runs (
                        id, created_at, format_id, agent_a, agent_b,
                        battle_count, base_seed, maximum_turns, timeout_seconds,
                        team_pool_path, agent_a_version, agent_b_version,
                        agent_a_git_commit, agent_b_git_commit,
                        agent_a_configuration_hash, agent_b_configuration_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._run_values(run_id, created_at, config),
                )

    def _run_values(self, run_id: str, created_at: str, config: BenchmarkConfig):
        agent_a = build_agent_metadata(config.agent_a_name, config)
        agent_b = build_agent_metadata(config.agent_b_name, config)
        return (
                        run_id,
                        created_at,
                        config.format_id,
                        config.agent_a_name,
                        config.agent_b_name,
                        config.battle_count,
                        config.base_seed,
                        config.maximum_turns,
            config.timeout_seconds,
                        config.team_pool_path,
            agent_a.version,
            agent_b.version,
            agent_a.git_commit,
            agent_b.git_commit,
            agent_a.configuration_hash,
            agent_b.configuration_hash,
        )

    def save_battle(self, run_id: str, result: BattleBenchmarkResult) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO benchmark_battles (
                        id, run_id, pair_id, winner, turns, agent_a, agent_b,
                        team_a_id, team_b_id, seed, termination_reason,
                        illegal_action_count_a, illegal_action_count_b,
                        decision_error_count_a, decision_error_count_b,
                        duration_seconds, run_dir, average_decision_time_ms,
                        lead_a_id, lead_b_id, lead_a_pair_id, lead_b_pair_id, species_a, species_b,
                        archetype_a, archetype_b
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.battle_id,
                        run_id,
                        result.pair_id,
                        result.winner,
                        result.turns,
                        result.agent_a,
                        result.agent_b,
                        result.team_a_id,
                        result.team_b_id,
                        seed_to_text(result.seed),
                        result.termination_reason,
                        result.illegal_action_count_a,
                        result.illegal_action_count_b,
                        result.decision_error_count_a,
                        result.decision_error_count_b,
                        result.duration_seconds,
                        result.run_dir,
                        result.average_decision_time_ms,
                        result.lead_a_id,
                        result.lead_b_id,
                        result.lead_a_pair_id,
                        result.lead_b_pair_id,
                        text_tuple(result.species_a),
                        text_tuple(result.species_b),
                        result.archetype_a,
                        result.archetype_b,
                    ),
                )

    def load_battles(self, run_id: str) -> list[BattleBenchmarkResult]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM benchmark_battles WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
            return [self._hydrate_battle(row) for row in rows]

    def get_run_agents(self, run_id: str) -> tuple[str, str]:
        with closing(sqlite3.connect(self.database_path)) as connection:
            row = connection.execute(
                "SELECT agent_a, agent_b FROM benchmark_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Benchmark run not found: {run_id}")
            return row[0], row[1]

    def save_pair(self, run_id: str, pair: BattlePair) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO benchmark_pairs (
                        id, run_id, team_1_id, team_2_id, seed
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pair.pair_id,
                        run_id,
                        pair.team_1_id,
                        pair.team_2_id,
                        seed_to_text(pair.seed),
                    ),
                )

    def _initialize(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS benchmark_runs (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        format_id TEXT NOT NULL,
                        agent_a TEXT NOT NULL,
                        agent_b TEXT NOT NULL,
                        battle_count INTEGER NOT NULL,
                        base_seed INTEGER NOT NULL,
                        maximum_turns INTEGER NOT NULL,
                        timeout_seconds INTEGER NOT NULL DEFAULT 120,
                        team_pool_path TEXT NOT NULL
                        , agent_a_version TEXT NOT NULL DEFAULT ''
                        , agent_b_version TEXT NOT NULL DEFAULT ''
                        , agent_a_git_commit TEXT
                        , agent_b_git_commit TEXT
                        , agent_a_configuration_hash TEXT NOT NULL DEFAULT ''
                        , agent_b_configuration_hash TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS benchmark_pairs (
                        id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        team_1_id TEXT NOT NULL,
                        team_2_id TEXT NOT NULL,
                        seed TEXT NOT NULL,
                        FOREIGN KEY (run_id) REFERENCES benchmark_runs(id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS benchmark_battles (
                        id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        pair_id TEXT NOT NULL DEFAULT '',
                        winner TEXT,
                        turns INTEGER NOT NULL,
                        agent_a TEXT NOT NULL,
                        agent_b TEXT NOT NULL,
                        team_a_id TEXT NOT NULL,
                        team_b_id TEXT NOT NULL,
                        seed TEXT NOT NULL,
                        termination_reason TEXT NOT NULL,
                        illegal_action_count_a INTEGER NOT NULL,
                        illegal_action_count_b INTEGER NOT NULL,
                        decision_error_count_a INTEGER NOT NULL,
                        decision_error_count_b INTEGER NOT NULL,
                        duration_seconds REAL NOT NULL,
                        run_dir TEXT NOT NULL,
                        average_decision_time_ms REAL NOT NULL DEFAULT 0,
                        lead_a_id TEXT,
                        lead_b_id TEXT,
                        lead_a_pair_id TEXT,
                        lead_b_pair_id TEXT,
                        species_a TEXT NOT NULL DEFAULT '',
                        species_b TEXT NOT NULL DEFAULT '',
                        archetype_a TEXT,
                        archetype_b TEXT,
                        FOREIGN KEY (run_id) REFERENCES benchmark_runs(id)
                    )
                    """
                )
                self._ensure_column(connection, "benchmark_battles", "pair_id", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(
                    connection,
                    "benchmark_battles",
                    "average_decision_time_ms",
                    "REAL NOT NULL DEFAULT 0",
                )
                self._ensure_column(connection, "benchmark_battles", "lead_a_id", "TEXT")
                self._ensure_column(connection, "benchmark_battles", "lead_b_id", "TEXT")
                self._ensure_column(connection, "benchmark_battles", "lead_a_pair_id", "TEXT")
                self._ensure_column(connection, "benchmark_battles", "lead_b_pair_id", "TEXT")
                self._ensure_column(connection, "benchmark_battles", "species_a", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(connection, "benchmark_battles", "species_b", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(connection, "benchmark_battles", "archetype_a", "TEXT")
                self._ensure_column(connection, "benchmark_battles", "archetype_b", "TEXT")
                self._ensure_column(connection, "benchmark_runs", "timeout_seconds", "INTEGER NOT NULL DEFAULT 120")
                self._ensure_column(connection, "benchmark_runs", "agent_a_version", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(connection, "benchmark_runs", "agent_b_version", "TEXT NOT NULL DEFAULT ''")
                self._ensure_column(connection, "benchmark_runs", "agent_a_git_commit", "TEXT")
                self._ensure_column(connection, "benchmark_runs", "agent_b_git_commit", "TEXT")
                self._ensure_column(
                    connection,
                    "benchmark_runs",
                    "agent_a_configuration_hash",
                    "TEXT NOT NULL DEFAULT ''",
                )
                self._ensure_column(
                    connection,
                    "benchmark_runs",
                    "agent_b_configuration_hash",
                    "TEXT NOT NULL DEFAULT ''",
                )

    def _ensure_column(self, connection, table: str, column: str, definition: str) -> None:
        columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _hydrate_battle(self, row) -> BattleBenchmarkResult:
        seed = tuple(int(value) for value in row["seed"].split(","))
        return BattleBenchmarkResult(
            battle_id=row["id"],
            pair_id=row["pair_id"],
            seed=seed,  # type: ignore[arg-type]
            agent_a=row["agent_a"],
            agent_b=row["agent_b"],
            team_a_id=row["team_a_id"],
            team_b_id=row["team_b_id"],
            winner=row["winner"],
            turns=row["turns"],
            illegal_action_count_a=row["illegal_action_count_a"],
            illegal_action_count_b=row["illegal_action_count_b"],
            decision_error_count_a=row["decision_error_count_a"],
            decision_error_count_b=row["decision_error_count_b"],
            duration_seconds=row["duration_seconds"],
            termination_reason=row["termination_reason"],
            run_dir=row["run_dir"],
            average_decision_time_ms=row["average_decision_time_ms"],
            lead_a_id=row["lead_a_id"],
            lead_b_id=row["lead_b_id"],
            lead_a_pair_id=row["lead_a_pair_id"],
            lead_b_pair_id=row["lead_b_pair_id"],
            species_a=tuple_from_text(row["species_a"]),
            species_b=tuple_from_text(row["species_b"]),
            archetype_a=row["archetype_a"],
            archetype_b=row["archetype_b"],
        )
