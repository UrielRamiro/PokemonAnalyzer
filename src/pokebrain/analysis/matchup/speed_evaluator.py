from __future__ import annotations

from pokebrain.analysis.matchup.models import CandidateAction, TurnOrder


def compare_turn_order(
    action_a: CandidateAction,
    action_b: CandidateAction,
) -> TurnOrder:
    if action_a.move.priority > action_b.move.priority:
        return TurnOrder.A_FIRST
    if action_b.move.priority > action_a.move.priority:
        return TurnOrder.B_FIRST
    if action_a.effective_speed > action_b.effective_speed:
        return TurnOrder.A_FIRST
    if action_b.effective_speed > action_a.effective_speed:
        return TurnOrder.B_FIRST
    return TurnOrder.SPEED_TIE

