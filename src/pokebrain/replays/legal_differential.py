from __future__ import annotations

from pokebrain.battle.models import BattleAction
from pokebrain.replays.recovery_models import LegalActionDiffMetrics, LegalActionSet


class LegalActionDifferentialValidator:
    def compare(
        self,
        *,
        authoritative: tuple[BattleAction, ...],
        reconstructed: LegalActionSet,
        actual_action: BattleAction,
    ) -> LegalActionDiffMetrics:
        expected = set(authoritative)
        actual = set(reconstructed.actions)
        metrics = LegalActionDiffMetrics()
        if expected == actual:
            metrics.exact_matches += 1
        metrics.missing_actions += len(expected - actual)
        metrics.extra_actions += len(actual - expected)
        if actual_action not in actual:
            metrics.actual_action_missing += 1
        return metrics
