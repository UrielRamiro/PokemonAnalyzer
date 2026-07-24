from __future__ import annotations

from pokebrain.replay.models import DecisionRecord, DecisionRegret


def calculate_regret(record: DecisionRecord) -> DecisionRegret:
    scores = [evaluation.average_utility for evaluation in record.alternative_evaluations]
    scores.append(record.selected_evaluation.average_utility)
    best_score = max(scores) if scores else record.selected_evaluation.average_utility
    selected_score = record.selected_evaluation.average_utility
    regret = best_score - selected_score
    return DecisionRegret(
        selected_score=selected_score,
        best_available_score=best_score,
        regret=regret,
        classification=classify_regret(regret),
    )


def classify_regret(regret: float) -> str:
    if regret < 5:
        return "negligible"
    if regret < 20:
        return "small"
    if regret < 50:
        return "significant"
    return "critical"
