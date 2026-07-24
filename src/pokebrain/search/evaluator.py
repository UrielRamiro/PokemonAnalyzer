from __future__ import annotations

from typing import Protocol

from pokebrain.analysis.type_chart import type_multiplier
from pokebrain.battle.models import BattleState
from pokebrain.data.manager import DataManager
from pokebrain.search.models import StateEvaluation


WIN_SCORE = 1_000_000.0
LOSS_SCORE = -1_000_000.0


class StateEvaluator(Protocol):
    def evaluate(self, state: BattleState, perspective: str = "player") -> StateEvaluation:
        ...


class HeuristicStateEvaluator:
    def __init__(self, data_manager: DataManager | None = None) -> None:
        self.data_manager = data_manager or DataManager()

    def evaluate(self, state: BattleState, perspective: str = "player") -> StateEvaluation:
        if _side_lost(state.opponent):
            return _terminal(WIN_SCORE, "Opponent has no available Pokemon.")
        if _side_lost(state.player):
            return _terminal(LOSS_SCORE, "Player has no available Pokemon.")

        material = _remaining_count(state.player) - _remaining_count(state.opponent)
        hp = _hp_fraction(state.player) - _hp_fraction(state.opponent)
        position = self._active_matchup(state)
        hazards = _hazard_score(state)
        status = _status_score(state)
        speed = self._speed_score(state)
        total = material * 100 + hp * 30 + position * 20 + hazards * 10 + status * 10 + speed * 5
        return StateEvaluation(
            total_score=total,
            material_score=material,
            hp_score=hp,
            position_score=position,
            speed_score=speed,
            hazard_score=hazards,
            status_score=status,
            win_condition_score=0.0,
            reasons=(
                f"material {material:.2f}",
                f"hp {hp:.2f}",
                f"position {position:.2f}",
                f"hazards {hazards:.2f}",
            ),
        )

    def _active_matchup(self, state: BattleState) -> float:
        player = self.data_manager.species.get_by_id(state.player.active.set_data.species_id)
        opponent = self.data_manager.species.get_by_id(state.opponent.active.set_data.species_id)
        if player is None or opponent is None:
            return 0.0
        player_best = max(
            (type_multiplier(move.type_id, opponent.types) for move_id in state.player.active.set_data.moves if (move := self.data_manager.moves.get_by_id(move_id)) is not None),
            default=1.0,
        )
        opponent_best = max(
            (type_multiplier(move.type_id, player.types) for move_id in state.opponent.active.set_data.moves if (move := self.data_manager.moves.get_by_id(move_id)) is not None),
            default=1.0,
        )
        return (player_best - opponent_best) / 4

    def _speed_score(self, state: BattleState) -> float:
        player = self.data_manager.species.get_by_id(state.player.active.set_data.species_id)
        opponent = self.data_manager.species.get_by_id(state.opponent.active.set_data.species_id)
        if player is None or opponent is None:
            return 0.0
        return 1.0 if player.base_stats.speed >= opponent.base_stats.speed else -1.0


def _terminal(score: float, reason: str) -> StateEvaluation:
    return StateEvaluation(
        total_score=score,
        material_score=0,
        hp_score=0,
        position_score=0,
        speed_score=0,
        hazard_score=0,
        status_score=0,
        win_condition_score=score,
        reasons=(reason,),
    )


def _remaining_count(side) -> int:
    return sum(1 for member in side.team if member.species_id not in side.fainted_ids)


def _side_lost(side) -> bool:
    return _remaining_count(side) == 0 or side.active.current_hp <= 0 and len(side.team) <= len(side.fainted_ids) + 1


def _hp_fraction(side) -> float:
    values = [max(side.active.current_hp, 0)]
    return sum(values) / 100 if side.active.current_hp <= 100 else sum(values) / 400


def _hazard_score(state: BattleState) -> float:
    score = 0.0
    if state.opponent.stealth_rock:
        score += 0.5
    if state.player.stealth_rock:
        score -= 0.5
    score += (state.opponent.spikes_layers - state.player.spikes_layers) * 0.2
    return score


def _status_score(state: BattleState) -> float:
    score = 0.0
    if state.opponent.active.status:
        score += 0.3
    if state.player.active.status:
        score -= 0.3
    return score
