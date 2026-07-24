from __future__ import annotations

from pokebrain.battle.models import ActionSummary, ActionType, BattleAction, MoveDecision


class TextMoveDecisionRenderer:
    def render(self, decision: MoveDecision) -> str:
        lines = [
            f"Recommended action: {_format_action(decision.recommended_action)}",
            f"Confidence: {decision.confidence:.0%}",
            "",
            "Reasons:",
        ]
        lines.extend(f"- {reason}" for reason in decision.reasons)
        if decision.risks:
            lines.append("")
            lines.append("Risks:")
            lines.extend(f"- {risk}" for risk in decision.risks)

        alternatives = decision.alternatives[:5]
        if alternatives:
            lines.append("")
            lines.append("Alternatives:")
            lines.extend(_format_summary(summary) for summary in alternatives)

        lines.append("")
        lines.append("Limitations:")
        lines.extend(f"- {limitation}" for limitation in decision.limitations)
        return "\n".join(lines)


def _format_summary(summary: ActionSummary) -> str:
    return (
        f"- {_format_action(summary.action)} | "
        f"avg {summary.average_utility:.1f}, "
        f"worst {summary.worst_case_utility:.1f}, "
        f"best {summary.best_case_utility:.1f}"
    )


def _format_action(action: BattleAction) -> str:
    if action.action_type == ActionType.MOVE:
        return f"move {action.move_id}"
    return f"switch {action.switch_target_id}"
