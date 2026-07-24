from __future__ import annotations

from enum import Enum

from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.battle.evaluators import MoveEvaluator, SwitchEvaluator
from pokebrain.battle.models import (
    ActionEvaluation,
    ActionSummary,
    ActionType,
    BattleAction,
    BattleState,
    MoveDecision,
    ScenarioEvaluation,
)
from pokebrain.damage import CachedDamageEngine, DamageRequest, FieldState, ShowdownDamageEngine
from pokebrain.damage.engine import DamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.team.models import PokemonSet


class DecisionStyle(Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


LIMITATIONS = (
    "v1 evaluates one turn at a time.",
    "Opponent prediction is approximated by known legal actions.",
    "Status, setup, abilities, items and multi-turn effects are only partially scored.",
    "Full legality and battle sequencing still belong to Pokemon Showdown.",
)


class MoveDecisionEngine:
    def __init__(
        self,
        data_manager: DataManager | None = None,
        damage_engine: DamageEngine | None = None,
        action_generator: LegalActionGenerator | None = None,
    ) -> None:
        self.data_manager = data_manager or DataManager()
        self.damage_engine = damage_engine or CachedDamageEngine(ShowdownDamageEngine())
        self.action_generator = action_generator or LegalActionGenerator()
        self.move_evaluator = MoveEvaluator(self.damage_engine, self.data_manager)
        self.switch_evaluator = SwitchEvaluator(self.damage_engine, self.data_manager)

    def decide(
        self,
        state: BattleState,
        style: DecisionStyle = DecisionStyle.BALANCED,
    ) -> MoveDecision:
        player_actions = self.action_generator.generate(state)
        opponent_actions = self.action_generator.generate_for_side(state.opponent)
        summaries = tuple(
            self._summarize_action(state, player_action, opponent_actions)
            for player_action in player_actions
        )
        if not summaries:
            raise ValueError("BattleState has no legal actions.")

        ranked = tuple(sorted(summaries, key=lambda summary: _style_score(summary, style), reverse=True))
        confidence = _confidence(ranked, style)
        chosen = ranked[0]
        return MoveDecision(
            recommended_action=chosen.action,
            alternatives=ranked,
            confidence=confidence,
            reasons=chosen.reasons,
            risks=chosen.risks,
            limitations=LIMITATIONS,
        )

    def _summarize_action(
        self,
        state: BattleState,
        player_action: BattleAction,
        opponent_actions: tuple[BattleAction, ...],
    ) -> ActionSummary:
        direct = self._evaluate_player_action(state, player_action)
        scenarios = tuple(
            self._evaluate_scenario(state, direct, opponent_action)
            for opponent_action in opponent_actions
        )
        utilities = tuple(scenario.utility for scenario in scenarios) or (direct.score,)
        return ActionSummary(
            action=player_action,
            average_utility=sum(utilities) / len(utilities),
            worst_case_utility=min(utilities),
            best_case_utility=max(utilities),
            reasons=direct.reasons,
            risks=direct.risks,
        )

    def _evaluate_player_action(self, state: BattleState, action: BattleAction) -> ActionEvaluation:
        if action.action_type == ActionType.MOVE:
            if action.move_id is None:
                raise ValueError("Move action is missing move_id.")
            return self.move_evaluator.evaluate(state, action.move_id)
        if action.switch_target_id is None:
            raise ValueError("Switch action is missing switch_target_id.")
        target = _find_team_member(state.player.team, action.switch_target_id)
        if target is None:
            raise ValueError(f"Switch target not found: {action.switch_target_id}")
        return self.switch_evaluator.evaluate(state, target)

    def _evaluate_scenario(
        self,
        state: BattleState,
        player_evaluation: ActionEvaluation,
        opponent_action: BattleAction,
    ) -> ScenarioEvaluation:
        utility = player_evaluation.score
        defender = state.player.active.set_data
        defender_current_hp = state.player.active.current_hp

        if player_evaluation.action.action_type == ActionType.SWITCH:
            target_id = player_evaluation.action.switch_target_id
            target = _find_team_member(state.player.team, target_id or "")
            if target is not None:
                defender = target
                defender_current_hp = self.switch_evaluator._max_hp(target)

        if opponent_action.action_type == ActionType.MOVE and opponent_action.move_id is not None:
            incoming = self._incoming_damage(state, defender, opponent_action.move_id)
            incoming_average = (incoming.minimum_percent + incoming.maximum_percent) / 2
            utility -= incoming_average
            if incoming.maximum_damage >= defender_current_hp:
                utility -= 75
            elif incoming.maximum_percent >= 50:
                utility -= 25
        elif opponent_action.action_type == ActionType.SWITCH:
            utility -= 5

        return ScenarioEvaluation(
            player_action=player_evaluation.action,
            opponent_action=opponent_action,
            utility=utility,
        )

    def _incoming_damage(self, state: BattleState, defender: PokemonSet, move_id: str):
        move = self.data_manager.moves.get_by_id(move_id)
        if move is None or move.category == "Status":
            from pokebrain.battle.evaluators import _zero_damage

            return _zero_damage()
        return self.damage_engine.calculate(
            DamageRequest(
                generation=state.generation,
                attacker=state.opponent.active.set_data,
                defender=defender,
                move_id=move_id,
                field=FieldState(weather=state.weather, terrain=state.terrain),
            )
        )


def _find_team_member(team: tuple[PokemonSet, ...], species_id: str) -> PokemonSet | None:
    for member in team:
        if member.species_id == species_id:
            return member
    return None


def _style_score(summary: ActionSummary, style: DecisionStyle) -> float:
    if style == DecisionStyle.CONSERVATIVE:
        return summary.worst_case_utility
    if style == DecisionStyle.AGGRESSIVE:
        return summary.best_case_utility
    return (summary.average_utility + summary.worst_case_utility) / 2


def _confidence(ranked: tuple[ActionSummary, ...], style: DecisionStyle) -> float:
    if len(ranked) == 1:
        return 0.7
    gap = _style_score(ranked[0], style) - _style_score(ranked[1], style)
    return max(0.35, min(0.9, 0.45 + gap / 100))
