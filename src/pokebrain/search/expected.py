from __future__ import annotations

import time

from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.battle.models import ActionType, BattleAction, BattleState
from pokebrain.search.evaluator import StateEvaluator
from pokebrain.search.maximin import SEARCH_LIMITATIONS
from pokebrain.search.models import SearchConfig, SearchResult, SearchedActionValue
from pokebrain.search.policy import HeuristicOpponentPolicyModel, OpponentPolicyConfig, OpponentPolicyModel, WeightedAction
from pokebrain.search.pruner import StaticActionPruner
from pokebrain.search.transition import BattleTransitionModel


class ExpectedValueSearch:
    def __init__(
        self,
        legal_action_generator: LegalActionGenerator,
        transition_model: BattleTransitionModel,
        state_evaluator: StateEvaluator,
        opponent_policy: OpponentPolicyModel | None = None,
        action_pruner: StaticActionPruner | None = None,
        policy_config: OpponentPolicyConfig | None = None,
    ) -> None:
        self._legal_actions = legal_action_generator
        self._transition_model = transition_model
        self._state_evaluator = state_evaluator
        self._policy_config = policy_config or OpponentPolicyConfig()
        self._opponent_policy = opponent_policy or HeuristicOpponentPolicyModel(config=self._policy_config)
        self._action_pruner = action_pruner or StaticActionPruner()
        self._nodes = 0
        self._started_at = 0.0
        self._config = SearchConfig()
        self.last_policy_actions_expanded = 0
        self.last_policy_distribution: tuple[WeightedAction, ...] = ()

    def search(self, state: BattleState, config: SearchConfig | None = None) -> SearchResult:
        self._config = config or SearchConfig()
        self._nodes = 0
        self._started_at = time.perf_counter()
        self.last_policy_actions_expanded = 0
        self.last_policy_distribution = ()
        self._begin_search_scope()
        player_actions = self._action_pruner.prune(
            state,
            self._legal_actions.generate(state),
            self._config.maximum_player_actions,
        )
        opponent_legal = self._legal_actions.generate_for_side(state.opponent)
        predicted = self._opponent_policy.predict(state, None, opponent_legal)
        opponent_actions = _select_policy_actions(self._opponent_policy, predicted, self._policy_config.maximum_actions)
        self.last_policy_distribution = predicted
        self.last_policy_actions_expanded = len(opponent_actions)
        if not player_actions:
            raise ValueError("No legal player actions available for search.")
        if not opponent_actions:
            opponent_actions = (WeightedAction(BattleAction(ActionType.MOVE, move_id="splash"), 1.0, 0.0),)
        self._prefetch_damage(state, player_actions, tuple(item.action for item in opponent_actions))

        values: list[SearchedActionValue] = []
        principal: tuple[BattleAction, ...] = ()
        for player_action in player_actions:
            branch_values: list[tuple[float, WeightedAction]] = []
            for opponent_action in opponent_actions:
                if self._limit_reached():
                    break
                transitions = self._transition_model.resolve_turn(state, player_action, opponent_action.action)
                value = sum(
                    transition.probability
                    * self._evaluate_transition(transition.next_state, self._config.maximum_depth - 1)
                    for transition in transitions
                )
                branch_values.append((value, opponent_action))
            if not branch_values:
                score = self._state_evaluator.evaluate(state).total_score
                branch_values.append((score, opponent_actions[0]))
            expected_value = sum(value * weighted.probability for value, weighted in branch_values)
            worst_value, worst_response = min(branch_values, key=lambda item: item[0])
            final_value = (
                self._policy_config.expected_value_weight * expected_value
                + self._policy_config.worst_case_weight * worst_value
            )
            best_value = max(value for value, _action in branch_values)
            values.append(
                SearchedActionValue(
                    action=player_action,
                    expected_value=final_value,
                    worst_case_value=worst_value,
                    best_case_value=best_value,
                )
            )
            if not principal or final_value > max(item.expected_value for item in values[:-1]):
                principal = (player_action, worst_response.action)

        best = max(values, key=lambda item: item.expected_value)
        return SearchResult(
            best_action=best.action,
            value=best.expected_value,
            explored_nodes=self._nodes,
            depth_reached=self._config.maximum_depth,
            action_values=tuple(sorted(values, key=lambda item: item.expected_value, reverse=True)),
            principal_variation=principal,
            limitations=(
                "OpponentPolicyModel v1 uses deterministic heuristic probabilities.",
                "Search combines expected value with worst-case protection.",
                *SEARCH_LIMITATIONS,
            ),
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


def _select_policy_actions(policy: OpponentPolicyModel, weighted: tuple[WeightedAction, ...], maximum: int) -> tuple[WeightedAction, ...]:
    if hasattr(policy, "select_actions"):
        return policy.select_actions(weighted, maximum)
    return weighted[:maximum]


def _pass_action() -> BattleAction:
    return BattleAction(action_type=ActionType.MOVE, move_id="splash")
