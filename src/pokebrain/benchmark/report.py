from __future__ import annotations

import math
import statistics

from pokebrain.benchmark.models import (
    BattleBenchmarkResult,
    BenchmarkArchetypeRow,
    BenchmarkLeadRow,
    BenchmarkMatchupRow,
    BenchmarkReport,
    BenchmarkSpeciesRow,
)


def build_benchmark_report(
    run_id: str,
    results: list[BattleBenchmarkResult],
    primary_agent: str,
) -> BenchmarkReport:
    wins = sum(1 for result in results if result.winner == _winner_name_for_agent(primary_agent, result))
    losses = sum(
        1
        for result in results
        if result.winner is not None and result.winner != _winner_name_for_agent(primary_agent, result)
    )
    ties = len(results) - wins - losses
    total = len(results)
    turns = [result.turns for result in results]
    adjusted = calculate_win_rate(wins, losses, ties)
    ci = confidence_interval_95(adjusted, total)
    illegal_count = sum(result.illegal_action_count_a + result.illegal_action_count_b for result in results)
    crashes = sum(1 for result in results if result.termination_reason in {"agent_crash", "timeout"})
    protocol_errors = sum(1 for result in results if result.termination_reason == "protocol_error")
    decision_times = [result.average_decision_time_ms for result in results if result.average_decision_time_ms > 0]

    return BenchmarkReport(
        run_id=run_id,
        total_battles=total,
        wins=wins,
        losses=losses,
        ties=ties,
        win_rate=wins / total if total else 0.0,
        loss_rate=losses / total if total else 0.0,
        tie_rate=ties / total if total else 0.0,
        adjusted_win_rate=adjusted,
        confidence_interval_95=ci,
        average_turns=sum(turns) / total if total else 0.0,
        median_turns=statistics.median(turns) if turns else 0.0,
        illegal_action_rate=illegal_count / total if total else 0.0,
        crash_rate=crashes / total if total else 0.0,
        protocol_error_rate=protocol_errors / total if total else 0.0,
        average_decision_time_ms=sum(decision_times) / len(decision_times) if decision_times else 0.0,
        matchup_rows=build_team_matchup_rows(results, primary_agent),
        lead_rows=build_lead_rows(results, primary_agent),
        opponent_species_rows=build_opponent_species_rows(results, primary_agent),
        archetype_rows=build_archetype_rows(results, primary_agent),
        self_play_warning=build_self_play_warning(results, primary_agent, adjusted),
        battle_results=tuple(results),
    )


def calculate_win_rate(wins: int, losses: int, ties: int) -> float:
    total = wins + losses + ties
    if total == 0:
        return 0.0
    return (wins + 0.5 * ties) / total


def confidence_interval_95(win_rate: float, battle_count: int) -> tuple[float, float]:
    if battle_count == 0:
        return (0.0, 0.0)
    standard_error = math.sqrt(win_rate * (1 - win_rate) / battle_count)
    margin = 1.96 * standard_error
    return (max(0.0, win_rate - margin), min(1.0, win_rate + margin))


def _winner_name_for_agent(agent_name: str, result: BattleBenchmarkResult) -> str:
    if result.agent_a == agent_name:
        return "PokeBrain"
    if result.agent_b == agent_name:
        return "Opponent"
    return agent_name


def build_team_matchup_rows(
    results: list[BattleBenchmarkResult],
    primary_agent: str,
) -> tuple[BenchmarkMatchupRow, ...]:
    team_ids = sorted({result.team_a_id for result in results} | {result.team_b_id for result in results})
    rows: list[BenchmarkMatchupRow] = []
    for team_id in team_ids:
        team_results = [
            result
            for result in results
            if (result.agent_a == primary_agent and result.team_a_id == team_id)
            or (result.agent_b == primary_agent and result.team_b_id == team_id)
        ]
        if not team_results:
            continue
        wins = sum(1 for result in team_results if result.winner == _winner_name_for_agent(primary_agent, result))
        losses = sum(
            1
            for result in team_results
            if result.winner is not None and result.winner != _winner_name_for_agent(primary_agent, result)
        )
        ties = len(team_results) - wins - losses
        rows.append(
            BenchmarkMatchupRow(
                team_id=team_id,
                battles=len(team_results),
                wins=wins,
                losses=losses,
                ties=ties,
                adjusted_win_rate=calculate_win_rate(wins, losses, ties),
            )
        )
    return tuple(rows)


def build_lead_rows(
    results: list[BattleBenchmarkResult],
    primary_agent: str,
) -> tuple[BenchmarkLeadRow, ...]:
    lead_ids = sorted({lead for result in results for lead in (_primary_lead(result, primary_agent),) if lead})
    rows: list[BenchmarkLeadRow] = []
    for lead_id in lead_ids:
        lead_results = [result for result in results if _primary_lead(result, primary_agent) == lead_id]
        wins = sum(1 for result in lead_results if result.winner == _winner_name_for_agent(primary_agent, result))
        losses = sum(
            1
            for result in lead_results
            if result.winner is not None and result.winner != _winner_name_for_agent(primary_agent, result)
        )
        ties = len(lead_results) - wins - losses
        rows.append(
            BenchmarkLeadRow(
                lead_id=lead_id,
                battles=len(lead_results),
                wins=wins,
                losses=losses,
                ties=ties,
                adjusted_win_rate=calculate_win_rate(wins, losses, ties),
            )
        )
    return tuple(rows)


def build_self_play_warning(
    results: list[BattleBenchmarkResult],
    primary_agent: str,
    adjusted_win_rate: float,
) -> str | None:
    if not results:
        return None
    if not all(result.agent_a == result.agent_b == primary_agent for result in results):
        return None
    if abs(adjusted_win_rate - 0.5) <= 0.1:
        return None
    return "Self-play is far from 50%; check side bias, team sampling or protocol handling."


def _primary_lead(result: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if result.agent_a == primary_agent:
        return result.lead_a_id
    if result.agent_b == primary_agent:
        return result.lead_b_id
    return None


def build_opponent_species_rows(
    results: list[BattleBenchmarkResult],
    primary_agent: str,
) -> tuple[BenchmarkSpeciesRow, ...]:
    species_ids = sorted({species for result in results for species in _opponent_species(result, primary_agent)})
    rows: list[BenchmarkSpeciesRow] = []
    for species_id in species_ids:
        species_results = [result for result in results if species_id in _opponent_species(result, primary_agent)]
        wins, losses, ties = _record_for(species_results, primary_agent)
        rows.append(
            BenchmarkSpeciesRow(
                species_id=species_id,
                battles=len(species_results),
                wins=wins,
                losses=losses,
                ties=ties,
                adjusted_win_rate=calculate_win_rate(wins, losses, ties),
            )
        )
    return tuple(rows)


def build_archetype_rows(
    results: list[BattleBenchmarkResult],
    primary_agent: str,
) -> tuple[BenchmarkArchetypeRow, ...]:
    archetypes = sorted({archetype for result in results for archetype in (_opponent_archetype(result, primary_agent),) if archetype})
    rows: list[BenchmarkArchetypeRow] = []
    for archetype in archetypes:
        archetype_results = [result for result in results if _opponent_archetype(result, primary_agent) == archetype]
        wins, losses, ties = _record_for(archetype_results, primary_agent)
        rows.append(
            BenchmarkArchetypeRow(
                archetype=archetype,
                battles=len(archetype_results),
                wins=wins,
                losses=losses,
                ties=ties,
                adjusted_win_rate=calculate_win_rate(wins, losses, ties),
            )
        )
    return tuple(rows)


def _opponent_species(result: BattleBenchmarkResult, primary_agent: str) -> tuple[str, ...]:
    if result.agent_a == primary_agent:
        return result.species_b
    if result.agent_b == primary_agent:
        return result.species_a
    return ()


def _opponent_archetype(result: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if result.agent_a == primary_agent:
        return result.archetype_b
    if result.agent_b == primary_agent:
        return result.archetype_a
    return None


def _record_for(results: list[BattleBenchmarkResult], primary_agent: str) -> tuple[int, int, int]:
    wins = sum(1 for result in results if result.winner == _winner_name_for_agent(primary_agent, result))
    losses = sum(
        1
        for result in results
        if result.winner is not None and result.winner != _winner_name_for_agent(primary_agent, result)
    )
    ties = len(results) - wins - losses
    return wins, losses, ties
