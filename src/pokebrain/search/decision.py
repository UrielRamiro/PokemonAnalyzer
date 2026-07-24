from __future__ import annotations

from pokebrain.battle import MoveDecisionEngine
from pokebrain.battle.models import ActionSummary, BattleState, MoveDecision
from pokebrain.search.maximin import MaximinSearch
from pokebrain.search.models import SearchConfig, SearchResult


class SearchDecisionEngine:
    def __init__(
        self,
        search_engine: MaximinSearch,
        fallback_engine: MoveDecisionEngine | None = None,
        config: SearchConfig | None = None,
    ) -> None:
        self.search_engine = search_engine
        self.fallback_engine = fallback_engine or MoveDecisionEngine()
        self.config = config or SearchConfig()
        self.last_search_result: SearchResult | None = None
        self.last_fallback_used = False
        self.last_fallback_reason: str | None = None

    def decide(self, state: BattleState) -> MoveDecision:
        self.last_search_result = None
        self.last_fallback_used = False
        self.last_fallback_reason = None
        try:
            result = self.search_engine.search(state, self.config)
            self.last_search_result = result
            return _decision_from_search(result)
        except Exception as error:
            self.last_fallback_used = True
            self.last_fallback_reason = _fallback_reason(error)
            fallback = self.fallback_engine.decide(state)
            return MoveDecision(
                recommended_action=fallback.recommended_action,
                alternatives=fallback.alternatives,
                confidence=fallback.confidence,
                reasons=("Search failed; using one-turn fallback.", *fallback.reasons),
                risks=fallback.risks,
                limitations=("Search fallback path was used.", *fallback.limitations),
            )


def _fallback_reason(error: Exception) -> str:
    text = str(error).lower()
    if "damage" in text or "calculator" in text:
        return "damage_error"
    if "transition" in text:
        return "transition_error"
    return "fallback"


def _decision_from_search(result: SearchResult) -> MoveDecision:
    alternatives = tuple(
        ActionSummary(
            action=value.action,
            average_utility=value.expected_value,
            worst_case_utility=value.worst_case_value,
            best_case_utility=value.best_case_value,
            reasons=(f"Search expected value {value.expected_value:.1f}.",),
            risks=(),
        )
        for value in result.action_values
    )
    best_summary = alternatives[0] if alternatives else ActionSummary(
        action=result.best_action,
        average_utility=result.value,
        worst_case_utility=result.value,
        best_case_utility=result.value,
        reasons=(),
        risks=(),
    )
    return MoveDecision(
        recommended_action=result.best_action,
        alternatives=alternatives,
        confidence=_confidence(result),
        reasons=(
            f"Search depth {result.depth_reached}, explored {result.explored_nodes} nodes.",
            f"Principal variation: {_format_pv(result)}",
            *best_summary.reasons,
        ),
        risks=(),
        limitations=result.limitations,
    )


def _confidence(result: SearchResult) -> float:
    if len(result.action_values) < 2:
        return 0.65
    gap = result.action_values[0].expected_value - result.action_values[1].expected_value
    return max(0.35, min(0.9, 0.5 + gap / 200))


def _format_pv(result: SearchResult) -> str:
    if not result.principal_variation:
        return "none"
    return " -> ".join(_format_action(action) for action in result.principal_variation)


def _format_action(action) -> str:
    if action.move_id:
        return f"move {action.move_id}"
    return f"switch {action.switch_target_id}"
