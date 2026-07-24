from __future__ import annotations

from pokebrain.analysis.matchup.models import MatchupAnalysis, MatchupSide, TurnOrder


class TextMatchupRenderer:
    def render(self, analysis: MatchupAnalysis) -> str:
        lines: list[str] = []
        lines.append(f"{analysis.pokemon_a.pokemon_id} vs {analysis.pokemon_b.pokemon_id}")
        lines.append("")
        lines.append("Probable order:")
        if analysis.turn_order is TurnOrder.A_FIRST:
            lines.append(f"1. {analysis.pokemon_a.pokemon_id}")
            lines.append(f"2. {analysis.pokemon_b.pokemon_id}")
        elif analysis.turn_order is TurnOrder.B_FIRST:
            lines.append(f"1. {analysis.pokemon_b.pokemon_id}")
            lines.append(f"2. {analysis.pokemon_a.pokemon_id}")
        else:
            lines.append("Speed tie")

        lines.append("")
        self._side(lines, "Best option for", analysis.pokemon_a)
        lines.append("")
        self._side(lines, "Best option for", analysis.pokemon_b)

        lines.append("")
        lines.append("Verdict:")
        lines.append(analysis.verdict.value)
        lines.append("")
        lines.append(f"Confidence: {analysis.confidence:.0%}")
        lines.append("")
        lines.append("Reasons:")
        lines.extend(f"- {reason}" for reason in analysis.reasons)
        lines.append("")
        lines.append("Limitations:")
        lines.extend(f"- {limitation}" for limitation in analysis.limitations)
        return "\n".join(lines)

    def _side(self, lines: list[str], label: str, side: MatchupSide) -> None:
        lines.append(f"{label} {side.pokemon_id}:")
        move = side.best_move
        if move is None:
            lines.append("- no offensive move detected")
            return
        lines.append(f"- Move: {move.move_id}")
        lines.append(f"- Damage: {move.minimum_percent}%-{move.maximum_percent}%")
        lines.append(f"- OHKO chance: {move.ohko_chance:.1%}")
        if side.ko_range:
            lines.append(
                f"- KO range: optimistic {side.ko_range.optimistic_turns}, "
                f"guaranteed {side.ko_range.guaranteed_turns}"
            )

