from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActivePokemonState, BattleAction, BattleSideState, BattleState, MoveDecision
from pokebrain.battle.models import ActionSummary, ActionType
from pokebrain.battle_protocol.events import DamageEvent, ItemEvent, MoveEvent
from pokebrain.belief import (
    BeliefSearchConfig,
    BeliefSearchDecisionEngine,
    BeliefState,
    BridgeLatencyEstimator,
    DecisionContext,
    LayeredBeliefSearchDecisionEngine,
    OpponentScenarioGenerator,
    PokemonBelief,
    PrincipalVariationOrdering,
    SearchBudget,
    WeightedValue,
    normalize,
    reveal_item,
    reveal_move,
)
from pokebrain.belief.reducer import BeliefStateReducer
from pokebrain.damage import DamageResult
from pokebrain.search.models import SearchConfig, SearchResult, SearchedActionValue
from pokebrain.team.models import EVSpread, PokemonSet


class BeliefStateTest(unittest.TestCase):
    def test_revealed_item_collapses_item_distribution(self) -> None:
        belief = reveal_item(self._belief(), "choicespecs")

        self.assertEqual(belief.revealed_item, "choicespecs")
        self.assertEqual(belief.possible_items, (WeightedValue("choicespecs", 1.0),))

    def test_revealed_move_is_added_to_known_moves(self) -> None:
        belief = reveal_move(self._belief(), "dracometeor")

        self.assertIn("dracometeor", belief.revealed_moves)
        self.assertTrue(any(item.value == "dracometeor" for item in belief.possible_moves))

    def test_incompatible_hypotheses_are_removed(self) -> None:
        state = BeliefState(opponent_team=(self._belief(),))

        updated = BeliefStateReducer().apply(
            state,
            ItemEvent("p2a: Dragapult", "choicespecs"),
        )

        self.assertEqual(updated.opponent_team[0].possible_items, (WeightedValue("choicespecs", 1.0),))

    def test_probabilities_are_normalized(self) -> None:
        values = normalize((WeightedValue("a", 2.0), WeightedValue("b", 1.0)))

        self.assertAlmostEqual(sum(item.probability for item in values), 1.0)
        self.assertAlmostEqual(values[0].probability, 2 / 3)

    def test_boots_are_reduced_after_hazard_damage(self) -> None:
        state = BeliefState(opponent_team=(self._belief(),))

        updated = BeliefStateReducer().apply(
            state,
            DamageEvent("p2a: Dragapult", "88/100", source="Stealth Rock"),
        )

        self.assertFalse(any(item.value == "heavydutyboots" for item in updated.opponent_team[0].possible_items))
        self.assertAlmostEqual(sum(item.probability for item in updated.opponent_team[0].possible_items), 1.0)

    def test_search_considers_multiple_opponent_scenarios(self) -> None:
        state = self._state()
        belief = BeliefState(opponent_team=(self._belief(),))
        engine = BeliefSearchDecisionEngine(
            search_engine=FakeScenarioSearchEngine(),
            belief_config=BeliefSearchConfig(maximum_scenarios=2, minimum_probability=0.0),
        )

        decision = engine.decide(DecisionContext(state, belief))

        self.assertEqual(engine.last_scenario_count, 2)
        self.assertEqual(decision.recommended_action, BattleAction(ActionType.MOVE, move_id="earthquake"))

    def test_same_seed_produces_same_scenario_selection(self) -> None:
        state = self._state()
        belief = BeliefState(opponent_team=(self._belief(),))
        generator = OpponentScenarioGenerator()

        first = generator.generate(state, belief, BeliefSearchConfig(maximum_scenarios=3, minimum_probability=0.0))
        second = generator.generate(state, belief, BeliefSearchConfig(maximum_scenarios=3, minimum_probability=0.0))

        self.assertEqual(first, second)

    def test_timeout_returns_last_completed_depth(self) -> None:
        engine = self._layered_engine(
            (
                self._search_result("earthquake", 10.0, depth=1, interruption="completed"),
                self._search_result("dragontail", 999.0, depth=2, interruption="time_limit"),
            )
        )

        decision = engine.decide(DecisionContext(self._state(), BeliefState(opponent_team=(self._belief(),))))

        self.assertEqual(decision.recommended_action, BattleAction(ActionType.MOVE, move_id="earthquake"))
        self.assertEqual(engine.metrics.completed_depth, 1)
        self.assertEqual(engine.metrics.attempted_depth, 2)
        self.assertEqual(engine.metrics.incomplete_layers, 1)

    def test_incomplete_depth_does_not_replace_previous_result(self) -> None:
        engine = self._layered_engine(
            (
                self._search_result("earthquake", 10.0, depth=1, interruption="completed"),
                self._search_result("dragontail", 500.0, depth=2, interruption="time_limit"),
            )
        )

        decision = engine.decide(DecisionContext(self._state(), BeliefState(opponent_team=(self._belief(),))))

        self.assertEqual(decision.recommended_action, BattleAction(ActionType.MOVE, move_id="earthquake"))

    def test_search_uses_at_most_one_batch_per_layer(self) -> None:
        damage = FakeLayeredDamageEngine()
        engine = self._layered_engine(
            (
                self._search_result("earthquake", 10.0, depth=1),
                self._search_result("earthquake", 20.0, depth=2),
            ),
            damage_engine=damage,
        )

        engine.decide(DecisionContext(self._state(), BeliefState(opponent_team=(self._belief(),))))

        self.assertLessEqual(engine.metrics.batches_by_depth.get(1, 0), 1)
        self.assertLessEqual(engine.metrics.batches_by_depth.get(2, 0), 1)

    def test_principal_variation_is_searched_first(self) -> None:
        earthquake = BattleAction(ActionType.MOVE, move_id="earthquake")
        dragontail = BattleAction(ActionType.MOVE, move_id="dragontail")

        ordered = PrincipalVariationOrdering().order((dragontail, earthquake), (earthquake,))

        self.assertEqual(ordered[0], earthquake)

    def test_batch_is_not_started_without_enough_budget(self) -> None:
        damage = FakeLayeredDamageEngine()
        engine = self._layered_engine(
            (self._search_result("earthquake", 10.0, depth=1),),
            damage_engine=damage,
            estimator=BridgeLatencyEstimator(average_base_ms=10_000.0, average_per_request_ms=100.0),
            config=SearchConfig(maximum_depth=1, maximum_nodes=10, maximum_time_ms=10, maximum_player_actions=3, maximum_opponent_actions=3),
        )

        engine.decide(DecisionContext(self._state(), BeliefState(opponent_team=(self._belief(),))))

        self.assertEqual(damage.batch_calls, 0)
        self.assertEqual(engine.metrics.timeout_before_batch, 1)

    def test_same_state_produces_same_action_with_layered_scheduler(self) -> None:
        context = DecisionContext(self._state(), BeliefState(opponent_team=(self._belief(),)))
        first = self._layered_engine((self._search_result("earthquake", 10.0, depth=1),)).decide(context)
        second = self._layered_engine((self._search_result("earthquake", 10.0, depth=1),)).decide(context)

        self.assertEqual(first.recommended_action, second.recommended_action)

    def _belief(self) -> PokemonBelief:
        return PokemonBelief(
            species_id="dragapult",
            possible_items=(WeightedValue("heavydutyboots", 0.4), WeightedValue("choicespecs", 0.35), WeightedValue("unknown", 0.25)),
            possible_abilities=(WeightedValue("infiltrator", 0.7), WeightedValue("clearbody", 0.3)),
            possible_moves=(WeightedValue("dracometeor", 0.5), WeightedValue("shadowball", 0.3), WeightedValue("uturn", 0.2)),
            possible_tera_types=(WeightedValue("Ghost", 0.5), WeightedValue("Dragon", 0.3), WeightedValue("unknown", 0.2)),
        )

    def _state(self) -> BattleState:
        player = PokemonSet("garchomp", None, None, None, 100, None, None, ("earthquake",), EVSpread())
        opponent = PokemonSet("dragapult", None, None, None, 100, None, None, (), EVSpread())
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=1,
            player=BattleSideState(ActivePokemonState(player, 100), (player,)),
            opponent=BattleSideState(ActivePokemonState(opponent, 100), (opponent,)),
        )

    def _search_result(self, move_id: str, value: float, depth: int, interruption: str = "completed") -> SearchResult:
        action = BattleAction(ActionType.MOVE, move_id=move_id)
        return SearchResult(
            best_action=action,
            value=value,
            explored_nodes=1,
            depth_reached=depth,
            action_values=(SearchedActionValue(action, value, value, value),),
            principal_variation=(action,),
            limitations=(),
            interruption_reason=interruption,
        )

    def _layered_engine(
        self,
        results: tuple[SearchResult, ...],
        damage_engine=None,
        estimator: BridgeLatencyEstimator | None = None,
        config: SearchConfig | None = None,
    ) -> LayeredBeliefSearchDecisionEngine:
        return LayeredBeliefSearchDecisionEngine(
            search_engine=FakeSearchDecisionEngine(results),
            damage_engine=damage_engine or FakeLayeredDamageEngine(),
            state_evaluator=FakeStateEvaluator(),
            belief_config=BeliefSearchConfig(maximum_scenarios=1, minimum_probability=0.0),
            search_config=config or SearchConfig(maximum_depth=2, maximum_nodes=10, maximum_time_ms=1000, maximum_player_actions=3, maximum_opponent_actions=3),
            bridge_latency_estimator=estimator,
        )


class FakeScenarioSearchEngine:
    last_search_result = None
    last_fallback_used = False
    last_fallback_reason = None

    def decide(self, state: BattleState) -> MoveDecision:
        item = state.opponent.active.set_data.item_id
        value = 100.0 if item == "heavydutyboots" else 20.0
        action = BattleAction(ActionType.MOVE, move_id="earthquake")
        return MoveDecision(
            recommended_action=action,
            alternatives=(
                ActionSummary(
                    action=action,
                    average_utility=value,
                    worst_case_utility=value,
                    best_case_utility=value,
                    reasons=(),
                    risks=(),
                ),
            ),
            confidence=0.5,
            reasons=(),
            risks=(),
            limitations=(),
        )


class FakeSearchDecisionEngine:
    last_search_result = None
    last_fallback_used = False
    last_fallback_reason = None

    def __init__(self, results: tuple[SearchResult, ...]) -> None:
        self.search_engine = FakeInnerSearch(results)

    def decide(self, state: BattleState) -> MoveDecision:
        action = BattleAction(ActionType.MOVE, move_id="earthquake")
        return MoveDecision(
            recommended_action=action,
            alternatives=(ActionSummary(action, 0.0, 0.0, 0.0, (), ()),),
            confidence=0.1,
            reasons=("fake fallback",),
            risks=(),
            limitations=(),
        )


class FakeInnerSearch:
    def __init__(self, results: tuple[SearchResult, ...]) -> None:
        self.results = list(results)

    def search(self, state: BattleState, config: SearchConfig | None = None) -> SearchResult:
        if self.results:
            return self.results.pop(0)
        action = BattleAction(ActionType.MOVE, move_id="earthquake")
        return SearchResult(action, 0.0, 0, config.maximum_depth if config else 1, (SearchedActionValue(action, 0.0, 0.0, 0.0),), (action,), ())


class FakeLayeredDamageEngine:
    def __init__(self) -> None:
        from pokebrain.damage import DamageEngineMetrics

        self.metrics = DamageEngineMetrics()
        self.batch_calls = 0
        self.scenario_id = None

    def begin_search_scope(self, **kwargs) -> None:
        from pokebrain.damage import DamageEngineMetrics

        self.metrics = DamageEngineMetrics()

    def set_scenario_id(self, scenario_id: str | None) -> None:
        self.scenario_id = scenario_id

    def calculate(self, request):
        return self.calculate_many((request,))[0]

    def calculate_many(self, requests):
        self.batch_calls += 1
        self.metrics.requested_calculations += len(requests)
        self.metrics.unique_calculations += len(requests)
        self.metrics.cache_misses += len(requests)
        self.metrics.bridge_batches += 1
        self.metrics.bridge_requests += len(requests)
        self.metrics.total_bridge_time_ms += 1.0
        return tuple(
            DamageResult(
                generation=request.generation,
                attacker_id="a",
                defender_id="d",
                move_id=request.move_id,
                damage_rolls=(10,),
                minimum_damage=10,
                maximum_damage=10,
                defender_max_hp=100,
                minimum_percent=10.0,
                maximum_percent=10.0,
                description="fake",
                ohko_chance=0.0,
                classification="chip",
            )
            for request in requests
        )


class FakeStateEvaluator:
    pass


if __name__ == "__main__":
    unittest.main()
