from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle import (
    ActivePokemonState,
    BattleSideState,
    BattleState,
    LegalActionGenerator,
    MoveDecisionEngine,
)
from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.search import (
    ActionPruner,
    DeterministicBattleTransitionModel,
    HeuristicStateEvaluator,
    MaximinSearch,
    SearchConfig,
    SearchDecisionEngine,
)
from pokebrain.search.models import StateTransition
from pokebrain.damage import DamageResult
from pokebrain.team.models import EVSpread, PokemonSet


class SearchEngineTest(unittest.TestCase):
    def test_state_evaluator_scores_material_advantage(self) -> None:
        state = self._state()
        ahead = replace(
            state,
            opponent=replace(state.opponent, fainted_ids=("kingambit",)),
        )

        self.assertGreater(
            HeuristicStateEvaluator().evaluate(ahead).total_score,
            HeuristicStateEvaluator().evaluate(state).total_score,
        )

    def test_transition_applies_average_damage(self) -> None:
        state = self._state(
            player=self._set("greattusk", moves=("headlongrush",), evs=EVSpread(attack=252)),
            opponent=self._set("kingambit", moves=("suckerpunch",), evs=EVSpread(hp=252)),
            opponent_hp=100,
        )

        next_state = DeterministicBattleTransitionModel().resolve_turn(
            state,
            BattleAction(ActionType.MOVE, move_id="headlongrush"),
            BattleAction(ActionType.MOVE, move_id="suckerpunch"),
        )[0].next_state

        self.assertLess(next_state.opponent.active.current_hp, state.opponent.active.current_hp)

    def test_maximin_uses_opponents_bad_response_for_player(self) -> None:
        state = self._state(
            player=self._set("dragapult", moves=("shadowball",), evs=EVSpread(special_attack=252, speed=252)),
            opponent=self._set("kingambit", moves=("suckerpunch", "swordsdance"), evs=EVSpread(attack=252)),
            player_hp=40,
        )
        search = self._search()

        result = search.search(state, SearchConfig(maximum_depth=2, maximum_nodes=80, maximum_time_ms=5000))

        self.assertTrue(result.action_values)
        self.assertGreater(result.explored_nodes, 0)

    def test_search_respects_node_limit(self) -> None:
        result = self._search().search(self._state(), SearchConfig(maximum_depth=2, maximum_nodes=1, maximum_time_ms=500))

        self.assertLessEqual(result.explored_nodes, 2)

    def test_search_decision_engine_uses_fallback_when_search_fails(self) -> None:
        class BrokenSearch:
            def search(self, state, config=None):
                raise RuntimeError("boom")

        decision = SearchDecisionEngine(
            search_engine=BrokenSearch(),
            fallback_engine=MoveDecisionEngine(),
        ).decide(self._state())

        self.assertIn("fallback", " ".join(decision.reasons).lower())

    def test_same_state_produces_same_decision(self) -> None:
        engine = SearchDecisionEngine(self._search(), config=SearchConfig(maximum_depth=2, maximum_nodes=80))
        state = self._state()

        first = engine.decide(state).recommended_action
        second = engine.decide(state).recommended_action

        self.assertEqual(first, second)

    def test_cached_search_matches_uncached_search_result(self) -> None:
        state = self._state(
            player=self._set("garchomp", moves=("earthquake", "dragonclaw"), evs=EVSpread(attack=252)),
            opponent=self._set("kingambit", moves=("kowtowcleave", "suckerpunch"), evs=EVSpread(attack=252)),
        )
        config = SearchConfig(maximum_depth=2, maximum_nodes=30, maximum_time_ms=5000, maximum_player_actions=2, maximum_opponent_actions=2)
        uncached = self._search_with_damage(FakeSearchDamageEngine(), enable_prefetch=False).search(state, config)
        cached = self._search_with_damage(FakeSearchDamageEngine(), enable_prefetch=True).search(state, config)

        self.assertEqual(cached.best_action, uncached.best_action)
        self.assertEqual(cached.value, uncached.value)

    def _search(self) -> MaximinSearch:
        return MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(),
            state_evaluator=HeuristicStateEvaluator(),
            action_pruner=ActionPruner(),
        )

    def _search_with_damage(self, damage_engine, enable_prefetch: bool) -> MaximinSearch:
        return MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(
                damage_engine=damage_engine,
                enable_damage_prefetch=enable_prefetch,
            ),
            state_evaluator=HeuristicStateEvaluator(),
            action_pruner=ActionPruner(),
        )

    def _state(
        self,
        player: PokemonSet | None = None,
        opponent: PokemonSet | None = None,
        player_hp: int = 100,
        opponent_hp: int = 100,
    ) -> BattleState:
        player = player or self._set("garchomp", moves=("earthquake", "swordsdance"), evs=EVSpread(attack=252))
        opponent = opponent or self._set("kingambit", moves=("kowtowcleave", "suckerpunch"), evs=EVSpread(attack=252))
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=1,
            player=BattleSideState(
                active=ActivePokemonState(player, current_hp=player_hp),
                team=(player, self._set("corviknight", moves=("bodypress", "roost"))),
            ),
            opponent=BattleSideState(
                active=ActivePokemonState(opponent, current_hp=opponent_hp),
                team=(opponent,),
            ),
        )

    def _set(self, species_id: str, moves: tuple[str, ...], evs: EVSpread | None = None) -> PokemonSet:
        return PokemonSet(
            species_id=species_id,
            nickname=None,
            item_id=None,
            ability_id=None,
            level=100,
            nature=None,
            tera_type=None,
            moves=moves,
            evs=evs or EVSpread(),
        )


if __name__ == "__main__":
    unittest.main()


class FakeSearchDamageEngine:
    def calculate(self, request):
        return self.calculate_many((request,))[0]

    def calculate_many(self, requests):
        return tuple(self._result(request) for request in requests)

    def _result(self, request):
        maximum = {
            "earthquake": 80,
            "dragonclaw": 35,
            "kowtowcleave": 45,
            "suckerpunch": 30,
        }.get(request.move_id, 0)
        minimum = max(0, maximum - 10)
        return DamageResult(
            generation=request.generation,
            attacker_id="attacker",
            defender_id="defender",
            move_id=request.move_id,
            damage_rolls=(minimum, maximum),
            minimum_damage=minimum,
            maximum_damage=maximum,
            defender_max_hp=100,
            minimum_percent=float(minimum),
            maximum_percent=float(maximum),
            description="fake",
            ohko_chance=0.0,
            classification="chip",
        )
