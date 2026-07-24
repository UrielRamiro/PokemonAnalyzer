from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Protocol

from pokebrain.analysis.type_chart import type_multiplier
from pokebrain.battle.models import ActionType, BattleAction, BattleState
from pokebrain.data.manager import DataManager
from pokebrain.search.models import ActionProbability


@dataclass(frozen=True, slots=True)
class PolicyReason:
    code: str
    contribution: float
    description: str


@dataclass(frozen=True, slots=True)
class WeightedAction:
    action: BattleAction
    probability: float
    policy_score: float
    reasons: tuple[PolicyReason, ...] = ()


@dataclass(frozen=True, slots=True)
class OpponentPolicyConfig:
    maximum_actions: int = 4
    minimum_probability: float = 0.05
    expected_value_weight: float = 0.75
    worst_case_weight: float = 0.25
    temperature: float = 0.8


@dataclass(frozen=True, slots=True)
class PolicyCalibration:
    temperature: float = 0.8
    probability_floor: float = 0.05
    tactical_threat_floor: float = 0.01


@dataclass(frozen=True, slots=True)
class PolicyWeights:
    immediate_ko: float = 6.0
    expected_damage: float = 3.0
    survival: float = 0.35
    position_gain: float = 0.9
    setup_value: float = 0.2
    pivot_value: float = 0.35
    hazard_value: float = 1.6
    loss_risk: float = -5.0


@dataclass(frozen=True, slots=True)
class PolicyProfile:
    format_id: str
    rating_bucket: str | None
    weights: PolicyWeights
    calibration: PolicyCalibration


@dataclass(frozen=True, slots=True)
class PolicyModelVersion:
    format_id: str
    data_start: str
    data_end: str
    showdown_version: str
    model_version: str


class OpponentPolicyModel(Protocol):
    def predict(
        self,
        state: BattleState,
        scenario,
        legal_actions: tuple[BattleAction, ...],
    ) -> tuple[WeightedAction, ...]:
        ...


class UniformOpponentPolicy:
    def predict(
        self,
        state: BattleState,
        legal_actions: tuple[BattleAction, ...],
    ) -> tuple[ActionProbability, ...]:
        if not legal_actions:
            return ()
        probability = 1 / len(legal_actions)
        return tuple(ActionProbability(action=action, probability=probability) for action in legal_actions)


class HeuristicOpponentPolicyModel:
    def __init__(
        self,
        data_manager: DataManager | None = None,
        config: OpponentPolicyConfig | None = None,
        weights: PolicyWeights | None = None,
        profile: PolicyProfile | None = None,
    ) -> None:
        self.data_manager = data_manager or DataManager()
        base_config = config or OpponentPolicyConfig()
        if profile is not None:
            base_config = replace(
                base_config,
                minimum_probability=profile.calibration.probability_floor,
                temperature=profile.calibration.temperature,
            )
            weights = profile.weights
        self.config = base_config
        self.weights = weights or PolicyWeights()

    def predict(
        self,
        state: BattleState,
        scenario,
        legal_actions: tuple[BattleAction, ...],
    ) -> tuple[WeightedAction, ...]:
        if not legal_actions:
            return ()
        scored = tuple((action, *self._score_action(state, action)) for action in legal_actions)
        probabilities = softmax(tuple(score for _action, score, _reasons in scored), self.config.temperature)
        weighted = tuple(
            WeightedAction(action=action, probability=probability, policy_score=score, reasons=reasons)
            for (action, score, reasons), probability in zip(scored, probabilities)
        )
        return tuple(sorted(weighted, key=lambda item: item.probability, reverse=True))

    def select_actions(
        self,
        weighted_actions: tuple[WeightedAction, ...],
        maximum_actions: int | None = None,
    ) -> tuple[WeightedAction, ...]:
        maximum = maximum_actions or self.config.maximum_actions
        likely = [item for item in weighted_actions if item.probability >= self.config.minimum_probability]
        selected = list(likely[: max(1, maximum - 1)])
        critical = [
            item
            for item in weighted_actions
            if any(reason.code in {"immediate_ko", "priority_ko"} for reason in item.reasons)
        ]
        for item in (*critical, *weighted_actions):
            if item not in selected:
                selected.append(item)
            if len(selected) >= maximum:
                break
        total = sum(item.probability for item in selected)
        if total <= 0:
            return tuple(selected)
        return tuple(
            WeightedAction(item.action, item.probability / total, item.policy_score, item.reasons)
            for item in selected
        )

    def _score_action(self, state: BattleState, action: BattleAction) -> tuple[float, tuple[PolicyReason, ...]]:
        if action.action_type is ActionType.SWITCH:
            return self._score_switch(state, action)
        return self._score_move(state, action)

    def _score_move(self, state: BattleState, action: BattleAction) -> tuple[float, tuple[PolicyReason, ...]]:
        move = self.data_manager.moves.get_by_id(action.move_id or "")
        attacker = self.data_manager.species.get_by_id(state.opponent.active.set_data.species_id)
        defender = self.data_manager.species.get_by_id(state.player.active.set_data.species_id)
        if move is None or attacker is None or defender is None:
            return 0.0, ()
        reasons: list[PolicyReason] = []
        score = 0.0
        if move.category == "Status":
            if move.id in {"stealthrock", "spikes", "toxicspikes", "stickyweb"} and not state.player.stealth_rock:
                score += self.weights.hazard_value
                reasons.append(PolicyReason("hazard_setup", self.weights.hazard_value, "Sets entry hazards."))
            elif move.id in {"rapidspin", "defog", "mortalspin", "tidyup"} and (state.opponent.stealth_rock or state.opponent.spikes_layers):
                removal_score = self.weights.hazard_value * 0.875
                score += removal_score
                reasons.append(PolicyReason("hazard_removal", removal_score, "Removes own hazards."))
            else:
                score += self.weights.setup_value
                reasons.append(PolicyReason("status_option", self.weights.setup_value, "Status or setup option."))
            return score, tuple(reasons)

        effectiveness = type_multiplier(move.type_id, defender.types)
        stab = 1.5 if move.type_id in attacker.types else 1.0
        accuracy = 1.0 if move.accuracy is None else max(0.0, move.accuracy / 100)
        expected_damage_ratio = ((move.power or 0) / 100) * effectiveness * stab * accuracy
        damage_score = expected_damage_ratio * self.weights.expected_damage
        score += damage_score
        reasons.append(PolicyReason("expected_damage", damage_score, "Expected damage from power, STAB, accuracy and type effectiveness."))
        if effectiveness == 0:
            score += self.weights.loss_risk
            reasons.append(PolicyReason("immunity_risk", self.weights.loss_risk, "Move can hit an immunity."))
        if move.priority > 0:
            priority_score = self.weights.pivot_value + move.priority * 0.25
            score += priority_score
            reasons.append(PolicyReason("priority", priority_score, "Priority move."))
        if expected_damage_ratio >= max(0.4, state.player.active.current_hp / 100):
            ko_score = self.weights.immediate_ko
            score += ko_score
            reasons.append(PolicyReason("immediate_ko", ko_score, "Likely immediate KO."))
            if move.priority > 0:
                priority_ko_score = self.weights.immediate_ko * 0.25
                score += priority_ko_score
                reasons.append(PolicyReason("priority_ko", priority_ko_score, "Priority likely secures KO."))
        return score, tuple(reasons)

    def _score_switch(self, state: BattleState, action: BattleAction) -> tuple[float, tuple[PolicyReason, ...]]:
        target = next((member for member in state.opponent.team if member.species_id == action.switch_target_id), None)
        target_species = self.data_manager.species.get_by_id(action.switch_target_id or "")
        player_species = self.data_manager.species.get_by_id(state.player.active.set_data.species_id)
        if target is None or target_species is None or player_species is None:
            return 0.2, (PolicyReason("switch", 0.2, "Switch option."),)
        best_taken = max(
            (
                type_multiplier(move.type_id, target_species.types)
                for move_id in state.player.active.set_data.moves
                if (move := self.data_manager.moves.get_by_id(move_id)) is not None
            ),
            default=1.0,
        )
        score = self.weights.position_gain - best_taken * self.weights.survival
        reasons = [PolicyReason("defensive_switch", score, "Switch quality from rough defensive matchup.")]
        if target.item_id == "heavydutyboots":
            score += 0.2
            reasons.append(PolicyReason("hazard_resilience", 0.2, "Switch target resists hazard chip."))
        return score, tuple(reasons)


def softmax(scores: tuple[float, ...], temperature: float = 0.8) -> tuple[float, ...]:
    if not scores:
        return ()
    safe_temperature = max(0.05, temperature)
    maximum = max(scores)
    values = tuple(math.exp((score - maximum) / safe_temperature) for score in scores)
    total = sum(values)
    if total <= 0:
        probability = 1 / len(scores)
        return tuple(probability for _ in scores)
    return tuple(value / total for value in values)
