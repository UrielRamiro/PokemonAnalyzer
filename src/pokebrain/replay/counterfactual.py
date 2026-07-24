from __future__ import annotations

from pokebrain.battle.models import BattleAction, BattleState
from pokebrain.benchmark.agents import BattleAgent
from pokebrain.replay.models import CounterfactualResult


class CounterfactualSimulator:
    def simulate_action(
        self,
        state: BattleState,
        player_action: BattleAction,
        opponent_policy: BattleAgent,
        continuation_policy: BattleAgent,
        simulation_count: int,
        seed: int,
    ) -> CounterfactualResult:
        raise NotImplementedError(
            "Counterfactual continuation requires a forced-action Showdown runner; "
            "the Replay Analyzer v1 intentionally starts with regret and deterministic detectors."
        )
