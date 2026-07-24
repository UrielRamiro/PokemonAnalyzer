from __future__ import annotations

from pokebrain.benchmark.models import BenchmarkConfig, BenchmarkReport


class TextBenchmarkRenderer:
    def render(self, config: BenchmarkConfig, report: BenchmarkReport) -> str:
        lower, upper = report.confidence_interval_95
        return "\n".join(
            [
                "Benchmark concluido",
                "",
                f"{config.agent_a_name} vs {config.agent_b_name}",
                f"Formato: {config.format_id}",
                f"Run ID: {report.run_id}",
                f"Partidas: {report.total_battles}",
                "",
                f"Vitorias: {report.wins}",
                f"Derrotas: {report.losses}",
                f"Empates/sem vencedor: {report.ties}",
                "",
                f"Taxa ajustada: {_percent(report.adjusted_win_rate)}",
                f"Taxa bruta de vitoria: {_percent(report.win_rate)}",
                f"Turnos medios: {report.average_turns:.1f}",
                f"Turnos medianos: {report.median_turns:.1f}",
                f"Tempo medio de decisao: {report.average_decision_time_ms:.1f} ms",
                "",
                f"Acoes ilegais por partida: {report.illegal_action_rate:.2f}",
                f"Falhas do agente: {_percent(report.crash_rate)}",
                f"Erros de protocolo: {_percent(report.protocol_error_rate)}",
                "",
                "Intervalo aproximado de 95%:",
                f"{_percent(lower)}-{_percent(upper)}",
                "",
                "Por time:",
                *_matchup_lines(report),
                "",
                "Por lead:",
                *_lead_lines(report),
                "",
                "Por especie adversaria:",
                *_species_lines(report),
                "",
                "Por arquetipo adversario:",
                *_archetype_lines(report),
                *_warning_lines(report),
            ]
        )


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _matchup_lines(report: BenchmarkReport) -> list[str]:
    if not report.matchup_rows:
        return ["- sem dados por time"]
    return [
        (
            f"- {row.team_id}: {row.battles} partidas, "
            f"{_percent(row.adjusted_win_rate)} ajustado "
            f"({row.wins}V/{row.losses}D/{row.ties}E)"
        )
        for row in report.matchup_rows
    ]


def _lead_lines(report: BenchmarkReport) -> list[str]:
    if not report.lead_rows:
        return ["- sem dados por lead"]
    return [
        (
            f"- {row.lead_id}: {row.battles} partidas, "
            f"{_percent(row.adjusted_win_rate)} ajustado "
            f"({row.wins}V/{row.losses}D/{row.ties}E)"
        )
        for row in report.lead_rows
    ]


def _warning_lines(report: BenchmarkReport) -> list[str]:
    if not report.self_play_warning:
        return []
    return ["", f"Alerta: {report.self_play_warning}"]


def _species_lines(report: BenchmarkReport) -> list[str]:
    if not report.opponent_species_rows:
        return ["- sem dados por especie"]
    rows = sorted(report.opponent_species_rows, key=lambda row: (row.adjusted_win_rate, -row.battles))
    return [
        (
            f"- {row.species_id}: {row.battles} partidas, "
            f"{_percent(row.adjusted_win_rate)} ajustado "
            f"({row.wins}V/{row.losses}D/{row.ties}E)"
        )
        for row in rows[:12]
    ]


def _archetype_lines(report: BenchmarkReport) -> list[str]:
    if not report.archetype_rows:
        return ["- sem dados por arquetipo"]
    return [
        (
            f"- {row.archetype}: {row.battles} partidas, "
            f"{_percent(row.adjusted_win_rate)} ajustado "
            f"({row.wins}V/{row.losses}D/{row.ties}E)"
        )
        for row in report.archetype_rows
    ]
