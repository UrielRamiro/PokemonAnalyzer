from __future__ import annotations

import time
from dataclasses import dataclass, field

from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.battle.models import ActionSummary, BattleAction, MoveDecision
from pokebrain.belief.models import BeliefSearchConfig, DecisionContext, OpponentScenario
from pokebrain.belief.scenarios import OpponentScenarioGenerator
from pokebrain.damage.engine import DamageEngine
from pokebrain.search.decision import SearchDecisionEngine
from pokebrain.search.evaluator import StateEvaluator
from pokebrain.search.models import SearchConfig, SearchResult
from pokebrain.search.prefetch import SearchDamagePrefetcher
from pokebrain.search.pruner import StaticActionPruner


@dataclass(slots=True)
class SearchBudget:
    deadline_ns: int
    maximum_nodes: int
    nodes_used: int = 0

    def remaining_ms(self) -> float:
        return max(0.0, (self.deadline_ns - time.monotonic_ns()) / 1_000_000)

    def has_time_for(self, estimated_ms: float, safety_margin_ms: float = 30.0) -> bool:
        return self.remaining_ms() >= estimated_ms + safety_margin_ms


@dataclass(slots=True)
class BridgeLatencyEstimator:
    average_base_ms: float = 140.0
    average_per_request_ms: float = 6.0

    def estimate(self, request_count: int) -> float:
        return self.average_base_ms + self.average_per_request_ms * request_count

    def update(self, request_count: int, elapsed_ms: float) -> None:
        if request_count <= 0:
            return
        observed_per_request = max(0.0, (elapsed_ms - self.average_base_ms) / request_count)
        self.average_per_request_ms = self.average_per_request_ms * 0.8 + observed_per_request * 0.2
        self.average_base_ms = self.average_base_ms * 0.9 + min(elapsed_ms, self.average_base_ms) * 0.1


@dataclass(slots=True)
class LayeredSearchMetrics:
    completed_depth: int = 0
    attempted_depth: int = 0
    nodes_used: int = 0
    batches_by_depth: dict[int, int] = field(default_factory=dict)
    requests_by_depth: dict[int, int] = field(default_factory=dict)
    incomplete_layers: int = 0
    timeout_before_batch: int = 0
    timeout_after_batch: int = 0
    reused_previous_pv: int = 0
    transposition_hits: int = 0
    planning_time_ms: float = 0.0
    bridge_time_ms: float = 0.0
    resolving_time_ms: float = 0.0
    evaluating_time_ms: float = 0.0
    ordering_time_ms: float = 0.0


class PrincipalVariationOrdering:
    def order(
        self,
        actions: tuple[BattleAction, ...],
        previous_pv: tuple[BattleAction, ...],
    ) -> tuple[BattleAction, ...]:
        if not previous_pv:
            return actions
        preferred = previous_pv[0]
        if preferred not in actions:
            return actions
        return (preferred, *tuple(action for action in actions if action != preferred))


class LayeredBeliefSearchDecisionEngine:
    def __init__(
        self,
        search_engine: SearchDecisionEngine,
        damage_engine: DamageEngine,
        state_evaluator: StateEvaluator,
        scenario_generator: OpponentScenarioGenerator | None = None,
        belief_config: BeliefSearchConfig | None = None,
        search_config: SearchConfig | None = None,
        bridge_latency_estimator: BridgeLatencyEstimator | None = None,
    ) -> None:
        self.search_engine = search_engine
        self.damage_engine = damage_engine
        self.state_evaluator = state_evaluator
        self.scenario_generator = scenario_generator or OpponentScenarioGenerator()
        self.belief_config = belief_config or BeliefSearchConfig()
        self.search_config = search_config or SearchConfig(maximum_depth=2, maximum_nodes=24, maximum_time_ms=500, maximum_player_actions=3, maximum_opponent_actions=3)
        self.bridge_latency_estimator = bridge_latency_estimator or BridgeLatencyEstimator()
        self.legal_actions = LegalActionGenerator()
        self.prefetcher = SearchDamagePrefetcher()
        self.pruner = StaticActionPruner()
        self.pv_ordering = PrincipalVariationOrdering()
        self.metrics = LayeredSearchMetrics()
        self.last_scenario_count = 0
        self.last_assumptions: tuple[str, ...] = ()

    def decide(self, context: DecisionContext) -> MoveDecision:
        self.metrics = LayeredSearchMetrics()
        scenarios = self.scenario_generator.generate(context.observed_state, context.belief_state, self.belief_config)
        self.last_scenario_count = len(scenarios)
        self.last_assumptions = tuple(" | ".join(scenario.assumptions) for scenario in scenarios)
        self._begin_damage_scope()
        budget = SearchBudget(
            deadline_ns=time.monotonic_ns() + self.search_config.maximum_time_ms * 1_000_000,
            maximum_nodes=self.search_config.maximum_nodes,
        )
        best_completed: MoveDecision | None = None
        previous_pv: tuple[BattleAction, ...] = ()

        for depth in range(1, self.search_config.maximum_depth + 1):
            self.metrics.attempted_depth = depth
            if budget.remaining_ms() <= 0:
                self.metrics.incomplete_layers += 1
                break
            if not self._prefetch_depth(depth, scenarios, budget, previous_pv):
                self.metrics.incomplete_layers += 1
                break
            result = self._search_depth(depth, scenarios, budget)
            if result is None:
                self.metrics.incomplete_layers += 1
                break
            decision, completed, pv, nodes = result
            budget.nodes_used += nodes
            self.metrics.nodes_used = budget.nodes_used
            if not completed:
                self.metrics.incomplete_layers += 1
                break
            best_completed = decision
            previous_pv = pv
            self.metrics.completed_depth = depth

        if best_completed is not None:
            return best_completed
        return self._fallback_depth_one(context, scenarios)

    def _prefetch_depth(
        self,
        depth: int,
        scenarios: tuple[OpponentScenario, ...],
        budget: SearchBudget,
        previous_pv: tuple[BattleAction, ...],
    ) -> bool:
        started = time.perf_counter()
        requests = []
        for scenario in scenarios:
            player_actions = self.pruner.prune(
                scenario.resolved_state,
                self.legal_actions.generate(scenario.resolved_state),
                self.search_config.maximum_player_actions,
            )
            ordered_at = time.perf_counter()
            player_actions = self.pv_ordering.order(player_actions, previous_pv)
            self.metrics.ordering_time_ms += (time.perf_counter() - ordered_at) * 1000
            opponent_actions = self.pruner.prune(
                _swap_perspective(scenario.resolved_state),
                self.legal_actions.generate_for_side(scenario.resolved_state.opponent),
                self.search_config.maximum_opponent_actions,
            )
            requests.extend(self.prefetcher.collect_requests(scenario.resolved_state, player_actions, opponent_actions))
        self.metrics.planning_time_ms += (time.perf_counter() - started) * 1000
        self.metrics.requests_by_depth[depth] = len(requests)
        estimate = self.bridge_latency_estimator.estimate(len(requests))
        if requests and not budget.has_time_for(estimate):
            self.metrics.timeout_before_batch += 1
            return False
        before_batches = _metric(self.damage_engine, "bridge_batches")
        before_bridge_ms = _metric(self.damage_engine, "total_bridge_time_ms")
        bridge_started = time.perf_counter()
        self._set_scenario_id(f"layered-prefetch-depth-{depth}")
        if requests and hasattr(self.damage_engine, "calculate_many"):
            self.damage_engine.calculate_many(tuple(requests))
        else:
            for request in requests:
                self.damage_engine.calculate(request)
        elapsed_ms = (time.perf_counter() - bridge_started) * 1000
        self.bridge_latency_estimator.update(len(requests), elapsed_ms)
        self.metrics.bridge_time_ms += _metric(self.damage_engine, "total_bridge_time_ms") - before_bridge_ms
        self.metrics.batches_by_depth[depth] = _metric(self.damage_engine, "bridge_batches") - before_batches
        if budget.remaining_ms() <= 0:
            self.metrics.timeout_after_batch += 1
            return False
        return True

    def _search_depth(
        self,
        depth: int,
        scenarios: tuple[OpponentScenario, ...],
        budget: SearchBudget,
    ) -> tuple[MoveDecision, bool, tuple[BattleAction, ...], int] | None:
        weighted: dict[BattleAction, list[float]] = {}
        principal: tuple[BattleAction, ...] = ()
        completed = True
        nodes = 0
        started = time.perf_counter()
        for index, scenario in enumerate(scenarios):
            if budget.remaining_ms() <= 0:
                return None
            self._set_scenario_id(f"layered-{index + 1}")
            remaining_nodes = max(1, budget.maximum_nodes - budget.nodes_used - nodes)
            scenario_config = SearchConfig(
                maximum_depth=depth,
                maximum_nodes=remaining_nodes,
                maximum_time_ms=max(1, int(budget.remaining_ms())),
                maximum_player_actions=self.search_config.maximum_player_actions,
                maximum_opponent_actions=self.search_config.maximum_opponent_actions,
            )
            result = self.search_engine.search_engine.search(scenario.resolved_state, scenario_config)
            nodes += result.explored_nodes
            if not principal:
                principal = result.principal_variation
            if result.interruption_reason != "completed" and not (depth == 1 and result.action_values):
                completed = False
            for value in result.action_values:
                weighted.setdefault(value.action, []).append(scenario.probability * value.expected_value)
        self.metrics.resolving_time_ms += (time.perf_counter() - started) * 1000
        if not weighted:
            return None
        decision = self._decision_from_weighted(depth, weighted)
        return decision, completed, principal, nodes

    def _decision_from_weighted(self, depth: int, weighted: dict[BattleAction, list[float]]) -> MoveDecision:
        evaluating_started = time.perf_counter()
        ranked = sorted(((action, sum(values)) for action, values in weighted.items()), key=lambda item: item[1], reverse=True)
        alternatives = tuple(
            ActionSummary(
                action=action,
                average_utility=value,
                worst_case_utility=value,
                best_case_utility=value,
                reasons=(f"Layered belief value {value:.1f}.",),
                risks=(),
            )
            for action, value in ranked
        )
        self.metrics.evaluating_time_ms += (time.perf_counter() - evaluating_started) * 1000
        best = alternatives[0]
        return MoveDecision(
            recommended_action=best.action,
            alternatives=alternatives,
            confidence=0.55 if depth > 1 else 0.45,
            reasons=(
                f"Layered belief completed depth {depth}.",
                f"Evaluated {self.last_scenario_count} opponent belief scenarios.",
                *tuple(f"Scenario: {assumption}" for assumption in self.last_assumptions[:4]),
                *best.reasons,
            ),
            risks=(),
            limitations=(
                "Layered belief search returns the deepest completed iteration.",
                "Layer batching is implemented at root prefetch in v1.",
            ),
        )

    def _fallback_depth_one(self, context: DecisionContext, scenarios: tuple[OpponentScenario, ...]) -> MoveDecision:
        fallback = self.search_engine.decide(context.observed_state)
        return MoveDecision(
            recommended_action=fallback.recommended_action,
            alternatives=fallback.alternatives,
            confidence=fallback.confidence,
            reasons=("Layered search had no completed depth; using fallback.", *fallback.reasons),
            risks=fallback.risks,
            limitations=("Layered fallback path was used.", *fallback.limitations),
        )

    def _begin_damage_scope(self) -> None:
        if hasattr(self.damage_engine, "begin_search_scope"):
            self.damage_engine.begin_search_scope(clear_l1=True, reset_metrics=True)

    def _set_scenario_id(self, scenario_id: str | None) -> None:
        if hasattr(self.damage_engine, "set_scenario_id"):
            self.damage_engine.set_scenario_id(scenario_id)


def _metric(damage_engine: DamageEngine, name: str) -> float:
    metrics = getattr(damage_engine, "metrics", None)
    return float(getattr(metrics, name, 0.0)) if metrics is not None else 0.0


def _swap_perspective(state):
    from dataclasses import replace

    return replace(state, player=state.opponent, opponent=state.player)
