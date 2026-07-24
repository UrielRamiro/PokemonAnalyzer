from __future__ import annotations

from pokebrain.analysis.matchup import MatchupVerdict
from pokebrain.analysis.team_matchup.models import TeamMatchupAnalysis


SYMBOLS = {
    MatchupVerdict.A_FAVORED: "+",
    MatchupVerdict.B_FAVORED: "-",
    MatchupVerdict.EVEN: "0",
    MatchupVerdict.UNCERTAIN: "?",
}


class TextTeamMatchupRenderer:
    def render(self, analysis: TeamMatchupAnalysis) -> str:
        lines: list[str] = []
        lines.append("Team A vs Team B")
        lines.append("")
        lines.extend(self._matrix(analysis))
        lines.append("")
        lines.append("Legend: + favorable, - unfavorable, 0 even, ? uncertain")
        lines.append("")
        lines.append("Main threats to Team A:")
        lines.extend(self._threats(analysis.threats_to_team_a))
        lines.append("")
        lines.append("Best Team A responses:")
        for summary in sorted(analysis.team_a_summaries, key=lambda item: item.coverage_score, reverse=True):
            lines.append(
                f"- {summary.pokemon_id}: covers {len(summary.favorable_against)} "
                f"(score {summary.coverage_score:.2f})"
            )
        lines.append("")
        lines.append(f"Overall structural score for Team A: {analysis.overall_score_for_team_a:.2f}")
        if analysis.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in analysis.warnings)
        lines.append("")
        lines.append("Limitations:")
        lines.extend(f"- {limitation}" for limitation in analysis.limitations)
        return "\n".join(lines)

    def _matrix(self, analysis: TeamMatchupAnalysis) -> list[str]:
        column_width = max(10, *(len(name) for name in analysis.matrix.team_b_ids)) + 2
        row_width = max(12, *(len(name) for name in analysis.matrix.team_a_ids)) + 2
        lines = [
            "".ljust(row_width)
            + "".join(name[: column_width - 1].ljust(column_width) for name in analysis.matrix.team_b_ids)
        ]
        for pokemon_a in analysis.matrix.team_a_ids:
            row = pokemon_a[: row_width - 1].ljust(row_width)
            for pokemon_b in analysis.matrix.team_b_ids:
                cell = next(
                    item
                    for item in analysis.matrix.cells
                    if item.pokemon_a_id == pokemon_a and item.pokemon_b_id == pokemon_b
                )
                row += SYMBOLS[cell.analysis.verdict].ljust(column_width)
            lines.append(row)
        return lines

    def _threats(self, threats) -> list[str]:
        lines = []
        for threat in sorted(threats, key=lambda item: item.severity):
            lines.append(
                f"- {threat.threat_id}: {threat.severity}; "
                f"favorable answers: {', '.join(threat.favorable_answers) or 'none'}; "
                f"neutral: {', '.join(threat.neutral_answers) or 'none'}"
            )
        return lines

