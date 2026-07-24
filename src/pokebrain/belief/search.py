from __future__ import annotations

from pokebrain.battle.models import ActionSummary, MoveDecision
from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.belief.models import BeliefSearchConfig, DecisionContext
from pokebrain.belief.scenarios import OpponentScenarioGenerator
from pokebrain.damage.engine import DamageEngine
from pokebrain.search.prefetch import SearchDamagePrefetcher
from pokebrain.search.pruner import StaticActionPruner
from pokebrain.search.decision import SearchDecisionEngine
from pokebrain.search.models import SearchConfig


class BeliefSearchDecisionEngine:
    def __init__(
        self,
        search_engine: SearchDecisionEngine,
        scenario_generator: OpponentScenarioGenerator | None = None,
        belief_config: BeliefSearchConfig | None = None,
        damage_engine: DamageEngine | None = None,
        enable_global_prefetch: bool = False,
        global_search_config: SearchConfig | None = None,
    ) -> None:
        self.search_engine = search_engine
        self.scenario_generator = scenario_generator or OpponentScenarioGenerator()
        self.belief_config = belief_config or BeliefSearchConfig()
        self.damage_engine = damage_engine
        self.enable_global_prefetch = enable_global_prefetch
        self.global_search_config = global_search_config or SearchConfig(maximum_player_actions=3, maximum_opponent_actions=3)
        self.legal_actions = LegalActionGenerator()
        self.prefetcher = SearchDamagePrefetcher()
        self.prefetch_pruner = StaticActionPruner()
        self.last_scenario_count = 0
        self.last_assumptions: tuple[str, ...] = ()

    def decide(self, context: DecisionContext) -> MoveDecision:
        scenarios = self.scenario_generator.generate(context.observed_state, context.belief_state, self.belief_config)
        self.last_scenario_count = len(scenarios)
        self.last_assumptions = tuple(" | ".join(scenario.assumptions) for scenario in scenarios)
        self._begin_shared_damage_scope()
        self._global_prefetch(scenarios)
        weighted: dict[object, list[float]] = {}
        action_details: dict[object, object] = {}
        for index, scenario in enumerate(scenarios):
            self._set_scenario_id(f"scenario-{index + 1}")
            decision = self.search_engine.decide(scenario.resolved_state)
            for alternative in decision.alternatives:
                weighted.setdefault(alternative.action, []).append(scenario.probability * alternative.average_utility)
                action_details[alternative.action] = alternative.action
        self._set_scenario_id(None)
        if not weighted:
            fallback = self.search_engine.decide(context.observed_state)
            return fallback
        ranked_values = sorted(
            ((action, sum(values)) for action, values in weighted.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        alternatives = tuple(
            ActionSummary(
                action=action,  # type: ignore[arg-type]
                average_utility=value,
                worst_case_utility=value,
                best_case_utility=value,
                reasons=(f"Belief-weighted value {value:.1f}.",),
                risks=(),
            )
            for action, value in ranked_values
        )
        best = alternatives[0]
        return MoveDecision(
            recommended_action=best.action,
            alternatives=alternatives,
            confidence=0.5 if len(scenarios) > 1 else 0.65,
            reasons=(
                f"Evaluated {len(scenarios)} opponent belief scenarios.",
                *tuple(f"Scenario: {assumption}" for assumption in self.last_assumptions[:4]),
                *best.reasons,
            ),
            risks=(),
            limitations=(
                "BeliefState v1 treats item, ability, moves and Tera independently.",
                "EV inference is not modeled yet.",
            ),
        )

    def _begin_shared_damage_scope(self) -> None:
        if self.damage_engine is not None and hasattr(self.damage_engine, "begin_search_scope"):
            self.damage_engine.begin_search_scope(clear_l1=True, reset_metrics=True)

    def _set_scenario_id(self, scenario_id: str | None) -> None:
        if self.damage_engine is not None and hasattr(self.damage_engine, "set_scenario_id"):
            self.damage_engine.set_scenario_id(scenario_id)

    def _global_prefetch(self, scenarios) -> None:
        if not self.enable_global_prefetch or self.damage_engine is None:
            return
        requests = []
        for index, scenario in enumerate(scenarios):
            self._set_scenario_id(f"scenario-{index + 1}")
            player_actions = self.prefetch_pruner.prune(
                scenario.resolved_state,
                self.legal_actions.generate(scenario.resolved_state),
                self.global_search_config.maximum_player_actions,
            )
            opponent_actions = self.prefetch_pruner.prune(
                _swap_perspective(scenario.resolved_state),
                self.legal_actions.generate_for_side(scenario.resolved_state.opponent),
                self.global_search_config.maximum_opponent_actions,
            )
            requests.extend(self.prefetcher.collect_requests(scenario.resolved_state, player_actions, opponent_actions))
        self._set_scenario_id("global-prefetch")
        if requests and hasattr(self.damage_engine, "calculate_many"):
            self.damage_engine.calculate_many(tuple(requests))
        else:
            for request in requests:
                self.damage_engine.calculate(request)


def _swap_perspective(state):
    from dataclasses import replace

    return replace(state, player=state.opponent, opponent=state.player)
