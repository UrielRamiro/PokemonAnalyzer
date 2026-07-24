from __future__ import annotations

from dataclasses import dataclass

from pokebrain.benchmark.models import BattleBenchmarkResult
from pokebrain.benchmark.report import calculate_win_rate


@dataclass(frozen=True, slots=True)
class LossGroupRow:
    label: str
    battles: int
    wins: int
    losses: int
    ties: int
    adjusted_win_rate: float


@dataclass(frozen=True, slots=True)
class BenchmarkLossReport:
    run_id: str
    primary_agent: str
    battles: int
    losses: int
    wins: int
    ties: int
    worst_opponent_species: tuple[LossGroupRow, ...]
    worst_opponent_archetypes: tuple[LossGroupRow, ...]
    worst_own_leads: tuple[LossGroupRow, ...]
    worst_own_teams: tuple[LossGroupRow, ...]
    shortest_losses: tuple[BattleBenchmarkResult, ...]
    longest_losses: tuple[BattleBenchmarkResult, ...]
    termination_reasons: tuple[tuple[str, int], ...]


def build_loss_report(
    *,
    run_id: str,
    battles: tuple[BattleBenchmarkResult, ...],
    primary_agent: str,
    top: int = 10,
    minimum_battles: int = 3,
) -> BenchmarkLossReport:
    wins, losses, ties = _record_for(tuple(battles), primary_agent)
    lost_battles = tuple(battle for battle in battles if _is_primary_loss(battle, primary_agent))
    return BenchmarkLossReport(
        run_id=run_id,
        primary_agent=primary_agent,
        battles=len(battles),
        losses=losses,
        wins=wins,
        ties=ties,
        worst_opponent_species=_worst_rows(
            battles,
            primary_agent,
            values=lambda battle: _opponent_species(battle, primary_agent),
            top=top,
            minimum_battles=minimum_battles,
        ),
        worst_opponent_archetypes=_worst_rows(
            battles,
            primary_agent,
            values=lambda battle: _single(_opponent_archetype(battle, primary_agent)),
            top=top,
            minimum_battles=minimum_battles,
        ),
        worst_own_leads=_worst_rows(
            battles,
            primary_agent,
            values=lambda battle: _single(_own_lead(battle, primary_agent)),
            top=top,
            minimum_battles=minimum_battles,
        ),
        worst_own_teams=_worst_rows(
            battles,
            primary_agent,
            values=lambda battle: _single(_own_team(battle, primary_agent)),
            top=top,
            minimum_battles=minimum_battles,
        ),
        shortest_losses=tuple(sorted(lost_battles, key=lambda battle: (battle.turns, battle.battle_id))[:top]),
        longest_losses=tuple(sorted(lost_battles, key=lambda battle: (-battle.turns, battle.battle_id))[:top]),
        termination_reasons=_termination_reasons(lost_battles),
    )


class TextBenchmarkLossRenderer:
    def render(self, report: BenchmarkLossReport) -> str:
        return "\n".join(
            [
                "Resumo competitivo das derrotas",
                "",
                f"Run ID: {report.run_id}",
                f"Agente analisado: {report.primary_agent}",
                f"Partidas: {report.battles}",
                f"Registro: {report.wins}V/{report.losses}D/{report.ties}E",
                "",
                "Piores especies adversarias:",
                *_row_lines(report.worst_opponent_species),
                "",
                "Piores arquetipos adversarios:",
                *_row_lines(report.worst_opponent_archetypes),
                "",
                "Piores leads proprios:",
                *_row_lines(report.worst_own_leads),
                "",
                "Piores times proprios:",
                *_row_lines(report.worst_own_teams),
                "",
                "Motivos de termino nas derrotas:",
                *_termination_lines(report.termination_reasons),
                "",
                "Derrotas mais curtas:",
                *_battle_lines(report.shortest_losses, report.primary_agent),
                "",
                "Derrotas mais longas:",
                *_battle_lines(report.longest_losses, report.primary_agent),
            ]
        )


def _worst_rows(
    battles: tuple[BattleBenchmarkResult, ...],
    primary_agent: str,
    *,
    values,
    top: int,
    minimum_battles: int,
) -> tuple[LossGroupRow, ...]:
    labels = sorted({label for battle in battles for label in values(battle) if label})
    rows: list[LossGroupRow] = []
    for label in labels:
        grouped = tuple(battle for battle in battles if label in values(battle))
        if len(grouped) < minimum_battles:
            continue
        wins, losses, ties = _record_for(grouped, primary_agent)
        rows.append(
            LossGroupRow(
                label=label,
                battles=len(grouped),
                wins=wins,
                losses=losses,
                ties=ties,
                adjusted_win_rate=calculate_win_rate(wins, losses, ties),
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.adjusted_win_rate, -row.battles, row.label))[:top])


def _record_for(
    battles: tuple[BattleBenchmarkResult, ...],
    primary_agent: str,
) -> tuple[int, int, int]:
    wins = sum(1 for battle in battles if _is_primary_win(battle, primary_agent))
    losses = sum(1 for battle in battles if _is_primary_loss(battle, primary_agent))
    ties = len(battles) - wins - losses
    return wins, losses, ties


def _is_primary_win(battle: BattleBenchmarkResult, primary_agent: str) -> bool:
    if battle.agent_a == primary_agent:
        return battle.winner == "PokeBrain"
    if battle.agent_b == primary_agent:
        return battle.winner == "Opponent"
    return battle.winner == primary_agent


def _is_primary_loss(battle: BattleBenchmarkResult, primary_agent: str) -> bool:
    return battle.winner is not None and not _is_primary_win(battle, primary_agent)


def _opponent_species(battle: BattleBenchmarkResult, primary_agent: str) -> tuple[str, ...]:
    if battle.agent_a == primary_agent:
        return battle.species_b
    if battle.agent_b == primary_agent:
        return battle.species_a
    return ()


def _opponent_archetype(battle: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if battle.agent_a == primary_agent:
        return battle.archetype_b
    if battle.agent_b == primary_agent:
        return battle.archetype_a
    return None


def _own_lead(battle: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if battle.agent_a == primary_agent:
        return battle.lead_a_id
    if battle.agent_b == primary_agent:
        return battle.lead_b_id
    return None


def _own_team(battle: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if battle.agent_a == primary_agent:
        return battle.team_a_id
    if battle.agent_b == primary_agent:
        return battle.team_b_id
    return None


def _opponent_team(battle: BattleBenchmarkResult, primary_agent: str) -> str | None:
    if battle.agent_a == primary_agent:
        return battle.team_b_id
    if battle.agent_b == primary_agent:
        return battle.team_a_id
    return None


def _single(value: str | None) -> tuple[str, ...]:
    return (value,) if value else ()


def _termination_reasons(battles: tuple[BattleBenchmarkResult, ...]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for battle in battles:
        counts[battle.termination_reason] = counts.get(battle.termination_reason, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _row_lines(rows: tuple[LossGroupRow, ...]) -> list[str]:
    if not rows:
        return ["- sem dados suficientes"]
    return [
        (
            f"- {row.label}: {row.battles} partidas, {_percent(row.adjusted_win_rate)} ajustado "
            f"({row.wins}V/{row.losses}D/{row.ties}E)"
        )
        for row in rows
    ]


def _termination_lines(rows: tuple[tuple[str, int], ...]) -> list[str]:
    if not rows:
        return ["- nenhuma derrota com motivo registrado"]
    return [f"- {reason}: {count}" for reason, count in rows]


def _battle_lines(battles: tuple[BattleBenchmarkResult, ...], primary_agent: str) -> list[str]:
    if not battles:
        return ["- nenhuma derrota"]
    lines = []
    for battle in battles:
        lines.append(
            (
                f"- {battle.battle_id}: {battle.turns} turnos, "
                f"time {_own_team(battle, primary_agent) or 'n/a'} vs "
                f"{_opponent_team(battle, primary_agent) or 'n/a'}, "
                f"lead {_own_lead(battle, primary_agent) or 'n/a'}, "
                f"replay {battle.run_dir}"
            )
        )
    return lines


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"
