from __future__ import annotations

from pokebrain.analysis.models import TeamAnalysis


MOVE_NAMES = {
    "stealthrock": "Stealth Rock",
    "spikes": "Spikes",
    "toxicspikes": "Toxic Spikes",
    "stickyweb": "Sticky Web",
    "rapidspin": "Rapid Spin",
    "defog": "Defog",
    "mortalspin": "Mortal Spin",
    "tidyup": "Tidy Up",
    "courtchange": "Court Change",
}


class TextTeamAnalysisRenderer:
    def render(self, analysis: TeamAnalysis) -> str:
        lines: list[str] = []
        lines.append(
            f"Team {'valid' if analysis.validation.valid else 'invalid'} in {analysis.format_id}"
        )
        if analysis.parse_errors:
            lines.append("")
            lines.append("Parse errors:")
            lines.extend(f"- {error}" for error in analysis.parse_errors)
        if analysis.validation.problems:
            lines.append("")
            lines.append("Validation problems:")
            lines.extend(f"- {problem}" for problem in analysis.validation.problems)

        lines.append("")
        lines.append(f"Members interpreted: {analysis.member_count}")

        lines.append("")
        lines.append("Hazards:")
        self._presence(lines, "Stealth Rock", analysis.hazards.stealth_rock_users)
        self._presence(lines, "Spikes", analysis.hazards.spikes_users)
        self._presence(lines, "Toxic Spikes", analysis.hazards.toxic_spikes_users)
        self._presence(lines, "Sticky Web", analysis.hazards.sticky_web_users)

        lines.append("")
        lines.append("Removal:")
        if analysis.removal.removers:
            for remover in analysis.removal.removers:
                lines.append(f"- {remover.species_id}: {MOVE_NAMES.get(remover.move_id, remover.move_id)} ({remover.effect})")
        else:
            lines.append("- absent")

        lines.append("")
        lines.append("Speed control:")
        if analysis.speed_profile.entries:
            fastest = analysis.speed_profile.entries[0]
            lines.append(f"- Fastest Pokemon: {fastest.species_id} ({fastest.speed} Speed)")
        if analysis.speed_profile.priority:
            for item in analysis.speed_profile.priority:
                lines.append(f"- Priority: {item.species_id} / {item.move_id} (+{item.priority})")
        else:
            lines.append("- Priority: absent")

        lines.append("")
        lines.append("Recovery:")
        lines.append(f"- Reliable: {', '.join(analysis.recovery.reliable) or 'absent'}")
        lines.append(f"- Conditional: {', '.join(analysis.recovery.conditional) or 'absent'}")
        lines.append(f"- Draining: {', '.join(analysis.recovery.draining) or 'absent'}")
        lines.append(f"- Passive: {', '.join(analysis.recovery.passive) or 'absent'}")

        lines.append("")
        lines.append("Relevant weaknesses:")
        for summary in analysis.type_profile.summary:
            if summary.weaknesses >= 2:
                extra = f", {summary.quad_weaknesses} 4x" if summary.quad_weaknesses else ""
                lines.append(f"- {summary.attacking_type}: {summary.weaknesses} weaknesses{extra}")

        lines.append("")
        lines.append("Resistances:")
        for summary in analysis.type_profile.summary:
            if summary.resistances or summary.immunities:
                lines.append(
                    f"- {summary.attacking_type}: {summary.resistances} resists, "
                    f"{summary.immunities} immunities"
                )

        lines.append("")
        lines.append("Roles:")
        for assignment in analysis.roles:
            role_text = ", ".join(assignment.roles) if assignment.roles else "none detected"
            evidence = "; ".join(assignment.evidence)
            lines.append(f"- {assignment.species_id}: {role_text}" + (f" ({evidence})" if evidence else ""))

        if analysis.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in analysis.warnings)

        return "\n".join(lines)

    def _presence(self, lines: list[str], label: str, users: tuple[str, ...]) -> None:
        lines.append(f"- {label}: {'present (' + ', '.join(users) + ')' if users else 'absent'}")

