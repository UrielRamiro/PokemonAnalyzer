from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from pokebrain.benchmark.models import BattleBenchmarkResult, Seed
from pokebrain.benchmark.seed import seed_to_text
from pokebrain.benchmark.team_sampler import SampledTeam
from pokebrain.benchmark.team_features import classify_team_archetype, species_ids_from_team_file


class LocalShowdownBattleRunner:
    def __init__(self, root_dir: Path | str = ".") -> None:
        self.root_dir = Path(root_dir)

    def run(
        self,
        *,
        battle_id: str,
        pair_id: str,
        format_id: str,
        agent_a_name: str,
        agent_b_name: str,
        team_a: SampledTeam,
        team_b: SampledTeam,
        seed: Seed,
        maximum_turns: int,
        timeout_seconds: int,
    ) -> BattleBenchmarkResult:
        started_at = time.perf_counter()
        recovered = self._recover_existing_completed_result(
            battle_id=battle_id,
            pair_id=pair_id,
            format_id=format_id,
            agent_a_name=agent_a_name,
            agent_b_name=agent_b_name,
            team_a=team_a,
            team_b=team_b,
            seed=seed,
        )
        if recovered is not None:
            return recovered
        command = [
            _npm_command(),
            "run",
            "battle",
            "--",
            "--format",
            format_id,
            "--team-a",
            str(team_a.path),
            "--team-b",
            str(team_b.path),
            "--agent-a",
            agent_a_name,
            "--agent-b",
            agent_b_name,
            "--battle-id",
            battle_id,
            "--seed",
            seed_to_text(seed),
            "--maximum-turns",
            str(maximum_turns),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            duration = time.perf_counter() - started_at
            recovered = self._recover_existing_completed_result(
                battle_id=battle_id,
                pair_id=pair_id,
                format_id=format_id,
                agent_a_name=agent_a_name,
                agent_b_name=agent_b_name,
                team_a=team_a,
                team_b=team_b,
                seed=seed,
                duration=duration,
            )
            if recovered is not None:
                return recovered
            return BattleBenchmarkResult(
                battle_id=battle_id,
                pair_id=pair_id,
                seed=seed,
                agent_a=agent_a_name,
                agent_b=agent_b_name,
                team_a_id=team_a.team_id,
                team_b_id=team_b.team_id,
                winner=None,
                turns=0,
                illegal_action_count_a=0,
                illegal_action_count_b=0,
                decision_error_count_a=0,
                decision_error_count_b=0,
                duration_seconds=duration,
                termination_reason="timeout",
                run_dir="",
                species_a=species_ids_from_team_file(format_id, team_a.path),
                species_b=species_ids_from_team_file(format_id, team_b.path),
                archetype_a=classify_team_archetype(format_id, team_a.path),
                archetype_b=classify_team_archetype(format_id, team_b.path),
            )
        duration = time.perf_counter() - started_at
        if completed.returncode != 0:
            termination_reason = _classify_process_failure(completed.stderr + completed.stdout)
            return BattleBenchmarkResult(
                battle_id=battle_id,
                pair_id=pair_id,
                seed=seed,
                agent_a=agent_a_name,
                agent_b=agent_b_name,
                team_a_id=team_a.team_id,
                team_b_id=team_b.team_id,
                winner=None,
                turns=0,
                illegal_action_count_a=0,
                illegal_action_count_b=0,
                decision_error_count_a=1 if termination_reason == "agent_crash" else 0,
                decision_error_count_b=0,
                duration_seconds=duration,
                termination_reason=termination_reason,
                run_dir="",
                average_decision_time_ms=0.0,
            )

        result_path = self._find_result_path(battle_id)
        return self._result_from_path(
            result_path=result_path,
            pair_id=pair_id,
            format_id=format_id,
            agent_a_name=agent_a_name,
            agent_b_name=agent_b_name,
            team_a=team_a,
            team_b=team_b,
            duration=duration,
        )

    def _recover_existing_completed_result(
        self,
        *,
        battle_id: str,
        pair_id: str,
        format_id: str,
        agent_a_name: str,
        agent_b_name: str,
        team_a: SampledTeam,
        team_b: SampledTeam,
        seed: Seed,
        duration: float = 0.0,
    ) -> BattleBenchmarkResult | None:
        try:
            result_path = self._find_result_path(battle_id)
        except FileNotFoundError:
            return None
        with result_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if data.get("termination_reason") not in {"win", "tie", "turn_limit"}:
            return None
        return self._result_from_path(
            result_path=result_path,
            pair_id=pair_id,
            format_id=format_id,
            agent_a_name=agent_a_name,
            agent_b_name=agent_b_name,
            team_a=team_a,
            team_b=team_b,
            duration=duration,
            fallback_seed=seed,
        )

    def _result_from_path(
        self,
        *,
        result_path: Path,
        pair_id: str,
        format_id: str,
        agent_a_name: str,
        agent_b_name: str,
        team_a: SampledTeam,
        team_b: SampledTeam,
        duration: float,
        fallback_seed: Seed | None = None,
    ) -> BattleBenchmarkResult:
        with result_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        lead_a, lead_b = _extract_leads(result_path.parent)
        seed = data.get("seed", fallback_seed)
        return BattleBenchmarkResult(
            battle_id=data.get("battle_id", result_path.parent.name),
            pair_id=pair_id,
            seed=tuple(int(value) for value in seed),  # type: ignore[arg-type]
            agent_a=data.get("agent_a", agent_a_name),
            agent_b=data.get("agent_b", agent_b_name),
            team_a_id=team_a.team_id,
            team_b_id=team_b.team_id,
            winner=data.get("winner"),
            turns=int(data.get("turns", 0)),
            illegal_action_count_a=int(data.get("illegal_action_count_a", 0)),
            illegal_action_count_b=int(data.get("illegal_action_count_b", 0)),
            decision_error_count_a=int(data.get("decision_error_count_a", 0)),
            decision_error_count_b=int(data.get("decision_error_count_b", 0)),
            duration_seconds=duration,
            termination_reason=data.get("termination_reason", "unknown"),
            run_dir=data.get("run_dir", str(result_path.parent)),
            average_decision_time_ms=float(data.get("average_decision_time_ms", 0.0)),
            lead_a_id=lead_a,
            lead_b_id=lead_b,
            species_a=species_ids_from_team_file(format_id, team_a.path),
            species_b=species_ids_from_team_file(format_id, team_b.path),
            archetype_a=classify_team_archetype(format_id, team_a.path),
            archetype_b=classify_team_archetype(format_id, team_b.path),
        )

    def _find_result_path(self, battle_id: str) -> Path:
        matches = sorted((self.root_dir / "runs").glob(f"*/{battle_id}/result.json"))
        if not matches:
            raise FileNotFoundError(f"No result.json found for battle {battle_id}")
        return matches[-1]


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _classify_process_failure(output: str) -> str:
    lowered = output.lower()
    if "python agent exited" in lowered or "pokebrain.local_agent" in lowered:
        return "agent_crash"
    if "spawn eperm" in lowered:
        return "protocol_error"
    if "error:" in lowered and "local_battle_runner" in lowered:
        return "node_crash"
    return "protocol_error"


def _extract_leads(run_dir: Path) -> tuple[str | None, str | None]:
    states_path = run_dir / "states.jsonl"
    if not states_path.exists():
        return None, None
    leads: dict[str, str] = {}
    with states_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            entry = json.loads(line)
            player_id = entry.get("player_id")
            team = entry.get("request", {}).get("team", [])
            active = next((pokemon for pokemon in team if pokemon.get("active")), None)
            if player_id in {"p1", "p2"} and active and player_id not in leads:
                leads[player_id] = active.get("speciesId")
            if "p1" in leads and "p2" in leads:
                break
    return leads.get("p1"), leads.get("p2")
