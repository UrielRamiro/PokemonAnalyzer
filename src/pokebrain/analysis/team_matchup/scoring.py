from __future__ import annotations

from pokebrain.analysis.matchup import MatchupVerdict
from pokebrain.analysis.team_matchup.models import MatchupScore


def score_for_team_a(verdict: MatchupVerdict, confidence: float) -> MatchupScore:
    if verdict is MatchupVerdict.A_FAVORED:
        return MatchupScore(advantage=1.0, confidence=confidence, uncertain=False)
    if verdict is MatchupVerdict.B_FAVORED:
        return MatchupScore(advantage=-1.0, confidence=confidence, uncertain=False)
    if verdict is MatchupVerdict.UNCERTAIN:
        return MatchupScore(advantage=0.0, confidence=confidence, uncertain=True)
    return MatchupScore(advantage=0.0, confidence=confidence, uncertain=False)


def calculate_coverage_score(
    favorable: int,
    unfavorable: int,
    even: int,
    uncertain: int,
) -> float:
    total = favorable + unfavorable + even + uncertain
    if total == 0:
        return 0.0
    raw = favorable * 1.0 + even * 0.25 - unfavorable * 1.0
    return raw / total


def classify_threat(favorable_answer_count: int, neutral_answer_count: int) -> str:
    if favorable_answer_count == 0 and neutral_answer_count == 0:
        return "critical"
    if favorable_answer_count == 0:
        return "high"
    if favorable_answer_count == 1:
        return "moderate"
    return "covered"


def classify_switch_in(worst_case_percent: float) -> str:
    if worst_case_percent < 35:
        return "comfortable"
    if worst_case_percent < 50:
        return "possible"
    if worst_case_percent < 100:
        return "risky"
    return "unsafe"

