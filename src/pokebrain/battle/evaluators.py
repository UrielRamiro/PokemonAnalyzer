from __future__ import annotations

from pokebrain.battle.hazards import stealth_rock_percent
from pokebrain.battle.models import ActionEvaluation, ActionType, BattleAction, BattleState
from pokebrain.battle.weights import (
    MOVE_GUARANTEED_KO_BONUS,
    MOVE_POSSIBLE_KO_BONUS,
    MOVE_PRIORITY_BONUS,
    RELIABLE_RECOVERY_MOVES,
    SWITCH_HAS_RECOVERY_BONUS,
    SWITCH_KO_RANGE_PENALTY,
    SWITCH_OVER_HALF_DAMAGE_PENALTY,
    SWITCH_RESISTS_BEST_MOVE_BONUS,
    SWITCH_THREATENS_KO_BONUS,
)
from pokebrain.damage import DamageRequest, FieldState
from pokebrain.damage.derived import calculate_ohko_chance
from pokebrain.damage.engine import DamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.team.models import PokemonSet


class MoveEvaluator:
    def __init__(self, damage_engine: DamageEngine, data_manager: DataManager) -> None:
        self.damage_engine = damage_engine
        self.data_manager = data_manager

    def evaluate(self, state: BattleState, move_id: str) -> ActionEvaluation:
        move = self.data_manager.moves.get_by_id(move_id)
        if move is None or move.category == "Status":
            return ActionEvaluation(
                action=BattleAction(ActionType.MOVE, move_id=move_id),
                score=0.0,
                reasons=(f"{move_id} is not a direct damaging move in v1.",),
                risks=("Status and setup value is not fully modeled yet.",),
            )

        damage = self.damage_engine.calculate(
            DamageRequest(
                generation=state.generation,
                attacker=state.player.active.set_data,
                defender=state.opponent.active.set_data,
                move_id=move_id,
                field=FieldState(weather=state.weather, terrain=state.terrain),
            )
        )
        hit_chance = 1.0 if move.accuracy is None else move.accuracy / 100
        average_percent = (damage.minimum_percent + damage.maximum_percent) / 2
        score = average_percent * hit_chance
        reasons = [f"{move_id} deals {damage.minimum_percent}-{damage.maximum_percent}%."]
        risks: list[str] = []

        current_ko_chance = calculate_ohko_chance(
            damage.damage_rolls,
            state.opponent.active.current_hp,
        )
        if damage.minimum_damage >= state.opponent.active.current_hp:
            score += MOVE_GUARANTEED_KO_BONUS
            reasons.append("It guarantees a KO from the current HP.")
        elif damage.maximum_damage >= state.opponent.active.current_hp:
            score += MOVE_POSSIBLE_KO_BONUS
            reasons.append(f"It has {current_ko_chance:.1%} KO chance from current HP.")
        if move.priority > 0:
            score += MOVE_PRIORITY_BONUS
            reasons.append("It has positive priority.")
        if move.accuracy is not None and move.accuracy < 100:
            risks.append(f"{move_id} can miss ({move.accuracy}% accuracy).")
        if damage.maximum_damage == 0:
            risks.append("The target is immune.")
            score -= 100

        return ActionEvaluation(
            action=BattleAction(ActionType.MOVE, move_id=move_id),
            score=score,
            reasons=tuple(reasons),
            risks=tuple(risks),
        )


class SwitchEvaluator:
    def __init__(self, damage_engine: DamageEngine, data_manager: DataManager) -> None:
        self.damage_engine = damage_engine
        self.data_manager = data_manager

    def evaluate(self, state: BattleState, target: PokemonSet) -> ActionEvaluation:
        action = BattleAction(ActionType.SWITCH, switch_target_id=target.species_id)
        opponent_best = self._best_opponent_damage(state, target)
        target_hp = self._max_hp(target)
        hazard_percent = stealth_rock_percent(target, self.data_manager) if state.player.stealth_rock else 0.0
        incoming_percent = opponent_best.maximum_percent + hazard_percent
        score = 0.0
        reasons: list[str] = []
        risks: list[str] = []

        if opponent_best.maximum_percent < 50:
            score += SWITCH_RESISTS_BEST_MOVE_BONUS
            reasons.append("Switch target survives the opponent's best known hit comfortably.")
        if self._threatens(state, target):
            score += SWITCH_THREATENS_KO_BONUS
            reasons.append("Switch target threatens a KO or strong 2HKO.")
        if RELIABLE_RECOVERY_MOVES.intersection(target.moves):
            score += SWITCH_HAS_RECOVERY_BONUS
            reasons.append("Switch target has reliable recovery.")
        if incoming_percent > 50:
            score -= SWITCH_OVER_HALF_DAMAGE_PENALTY
            risks.append("Switch target may lose more than 50% on entry plus attack.")
        if incoming_percent >= 100:
            score -= SWITCH_KO_RANGE_PENALTY
            risks.append("Switch target can be KOed on entry sequence.")
        if hazard_percent:
            risks.append(f"Stealth Rock costs {hazard_percent}% on entry.")

        return ActionEvaluation(action=action, score=score, reasons=tuple(reasons), risks=tuple(risks))

    def _best_opponent_damage(self, state: BattleState, defender: PokemonSet):
        damages = []
        for move_id in state.opponent.active.set_data.moves:
            move = self.data_manager.moves.get_by_id(move_id)
            if move is None or move.category == "Status":
                continue
            damages.append(
                self.damage_engine.calculate(
                    DamageRequest(
                        generation=state.generation,
                        attacker=state.opponent.active.set_data,
                        defender=defender,
                        move_id=move_id,
                        field=FieldState(weather=state.weather, terrain=state.terrain),
                    )
                )
            )
        return max(damages, key=lambda result: result.maximum_percent, default=_zero_damage())

    def _threatens(self, state: BattleState, attacker: PokemonSet) -> bool:
        for move_id in attacker.moves:
            move = self.data_manager.moves.get_by_id(move_id)
            if move is None or move.category == "Status":
                continue
            damage = self.damage_engine.calculate(
                DamageRequest(
                    generation=state.generation,
                    attacker=attacker,
                    defender=state.opponent.active.set_data,
                    move_id=move_id,
                )
            )
            if damage.maximum_percent >= 50:
                return True
        return False

    def _max_hp(self, pokemon_set: PokemonSet) -> int:
        species = self.data_manager.species.get_by_id(pokemon_set.species_id)
        if species is None:
            return 1
        from pokebrain.analysis.stats import StatCalculator

        return StatCalculator().calculate(pokemon_set, species).hp


def _zero_damage():
    from pokebrain.damage import DamageResult

    return DamageResult(
        generation=0,
        attacker_id="",
        defender_id="",
        move_id="",
        damage_rolls=(0,),
        minimum_damage=0,
        maximum_damage=0,
        defender_max_hp=1,
        minimum_percent=0.0,
        maximum_percent=0.0,
        description="no damage",
        ohko_chance=0.0,
        classification="low_damage",
    )

