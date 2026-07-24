from __future__ import annotations

import time

from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.battle.models import ActionType, BattleAction, BattleState
from pokebrain.search.evaluator import StateEvaluator
from pokebrain.search.models import SearchConfig, SearchResult, SearchedActionValue
from pokebrain.search.pruner import ActionPruner
from pokebrain.search.transition import BattleTransitionModel


SEARCH_LIMITATIONS = (
    "Maximin assumes the opponent chooses the worst response for us.",
    "Depth is short and deterministic in v1.",
    "Transition model uses average damage and ignores secondary effects.",
    "Observed/opponent uncertainty interfaces are not fully populated yet.",
)


class MaximinSearch:
    def __init__(
        self,
        legal_action_generator: LegalActionGenerator,
        transition_model: BattleTransitionModel,
        state_evaluator: StateEvaluator,
        action_pruner: ActionPruner | None = None,
    ) -> None:
        self._legal_actions = legal_action_generator
        self._transition_model = transition_model
        self._state_evaluator = state_evaluator
        self._action_pruner = action_pruner or ActionPruner()
        self._nodes = 0
        self._started_at = 0.0
        self._config = SearchConfig()

    def search(
        self,
        state: BattleState,
        config: SearchConfig | None = None,
    ) -> SearchResult:
        self._config = config or SearchConfig()
        self._nodes = 0
        self._started_at = time.perf_counter()
        self._begin_search_scope()
        player_actions = self._action_pruner.prune(
            state,
            self._legal_actions.generate(state),
            self._config.maximum_player_actions,
        )
        action_priors = getattr(self._action_pruner, "last_scores", {})
        opponent_actions = self._action_pruner.prune(
            _swap_perspective(state),
            self._legal_actions.generate_for_side(state.opponent),
            self._config.maximum_opponent_actions,
        )
        if not player_actions:
            raise ValueError("No legal player actions available for search.")
        if not opponent_actions:
            opponent_actions = (BattleAction(player_actions[0].action_type, player_actions[0].move_id, player_actions[0].switch_target_id),)
        self._prefetch_damage(state, player_actions, opponent_actions)

        values: list[SearchedActionValue] = []
        principal: tuple[BattleAction, ...] = ()
        for player_action in player_actions:
            response_values: list[tuple[float, BattleAction]] = []
            for opponent_action in opponent_actions:
                if self._limit_reached():
                    break
                transitions = self._transition_model.resolve_turn(state, player_action, opponent_action)
                value = sum(
                    transition.probability
                    * self._evaluate_transition(transition.next_state, self._config.maximum_depth - 1)
                    for transition in transitions
                )
                response_values.append((value, opponent_action))
            if not response_values:
                score = self._state_evaluator.evaluate(state).total_score
                response_values.append((score, opponent_actions[0]))
            raw_worst_value, worst_response = min(response_values, key=lambda item: item[0])
            best_value = max(value for value, _action in response_values)
            prior = action_priors.get(player_action, 0.0)
            worst_value = raw_worst_value + prior * 0.35
            values.append(
                SearchedActionValue(
                    action=player_action,
                    expected_value=worst_value,
                    worst_case_value=worst_value,
                    best_case_value=best_value + prior * 0.35,
                )
            )
            if not principal or worst_value > max(item.expected_value for item in values[:-1]):
                principal = (player_action, worst_response)

        best = max(values, key=lambda item: item.expected_value)
        return SearchResult(
            best_action=best.action,
            value=best.expected_value,
            explored_nodes=self._nodes,
            depth_reached=self._config.maximum_depth,
            action_values=tuple(sorted(values, key=lambda item: item.expected_value, reverse=True)),
            principal_variation=principal,
            limitations=SEARCH_LIMITATIONS,
            interruption_reason=self._interruption_reason(),
        )

    def _evaluate_transition(self, state: BattleState, remaining_depth: int) -> float:
        self._nodes += 1
        if remaining_depth <= 0 or self._limit_reached():
            return self._state_evaluator.evaluate(state).total_score
        player_actions = self._action_pruner.prune(
            state,
            self._legal_actions.generate(state),
            self._config.maximum_player_actions,
        )
        if not player_actions:
            return self._state_evaluator.evaluate(state).total_score
        self._prefetch_damage(state, player_actions, (_pass_action(),))
        # Our next ply only: optimistic best continuation after the opponent response.
        return max(self._state_evaluator.evaluate(self._transition_model.resolve_turn(state, action, _pass_action())[0].next_state).total_score for action in player_actions)

    def _limit_reached(self) -> bool:
        if self._nodes >= self._config.maximum_nodes:
            return True
        elapsed_ms = (time.perf_counter() - self._started_at) * 1000
        return elapsed_ms >= self._config.maximum_time_ms

    def _interruption_reason(self) -> str:
        elapsed_ms = (time.perf_counter() - self._started_at) * 1000
        if elapsed_ms >= self._config.maximum_time_ms:
            return "time_limit"
        if self._nodes >= self._config.maximum_nodes:
            return "node_limit"
        return "completed"

    def _begin_search_scope(self) -> None:
        if hasattr(self._transition_model, "begin_search_scope"):
            self._transition_model.begin_search_scope()

    def _prefetch_damage(
        self,
        state: BattleState,
        player_actions: tuple[BattleAction, ...],
        opponent_actions: tuple[BattleAction, ...],
    ) -> None:
        if self._limit_reached():
            return
        if hasattr(self._transition_model, "prefetch_damage"):
            self._transition_model.prefetch_damage(state, player_actions, opponent_actions)



def _pass_action() -> BattleAction:
    return BattleAction(action_type=ActionType.MOVE, move_id="splash")


def _swap_perspective(state: BattleState) -> BattleState:
    from dataclasses import replace

    return replace(state, player=state.opponent, opponent=state.player)
