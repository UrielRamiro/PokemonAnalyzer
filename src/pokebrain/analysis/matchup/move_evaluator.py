from __future__ import annotations

from pokebrain.analysis.matchup.ko_classifier import (
    calculate_expected_damage,
    calculate_two_hko_chance,
    classify_move_damage,
)
from pokebrain.analysis.matchup.models import MoveMatchupResult
from pokebrain.damage import DamageEngine, DamageRequest, FieldState
from pokebrain.data.manager import DataManager
from pokebrain.data.models import Move
from pokebrain.team.models import PokemonSet


SPECIAL_CONTEXT_MOVES = {
    "suckerpunch": ("requires target to choose an offensive move",),
    "counter": ("requires previous physical damage",),
    "mirrorcoat": ("requires previous special damage",),
    "metalburst": ("requires previous damage this turn",),
    "futuresight": ("delayed damage",),
    "focuspunch": ("requires not being hit before attacking",),
    "foulplay": ("uses defender Attack stat",),
    "bodypress": ("uses attacker Defense stat",),
    "storedpower": ("requires boost context",),
    "electroball": ("requires exact speed context",),
    "gyroball": ("requires exact speed context",),
    "lowkick": ("depends on target weight",),
    "grassknot": ("depends on target weight",),
    "knockoff": ("depends on defender item state",),
    "facade": ("depends on attacker status",),
    "hex": ("depends on defender status",),
    "terablast": ("depends on Tera state",),
    "reversal": ("depends on current HP",),
    "flail": ("depends on current HP",),
    "lastrespects": ("depends on fainted allies",),
    "ragefist": ("depends on previous hits taken",),
}


class MoveMatchupEvaluator:
    def __init__(
        self,
        damage_engine: DamageEngine,
        data_manager: DataManager,
    ) -> None:
        self.damage_engine = damage_engine
        self.data_manager = data_manager

    def evaluate_moves(
        self,
        generation: int,
        attacker: PokemonSet,
        defender: PokemonSet,
        field: FieldState,
        format_id: str = "unknown",
    ) -> tuple[MoveMatchupResult, ...]:
        results: list[MoveMatchupResult] = []
        for move_id in attacker.moves:
            move = self.data_manager.moves.get_by_id(move_id)
            if move is None:
                continue
            if move.category == "Status":
                results.append(self._status_result(move))
                continue
            damage = self.damage_engine.calculate(
                DamageRequest(
                    generation=generation,
                    attacker=attacker,
                    defender=defender,
                    move_id=move_id,
                    field=field,
                    format_id=format_id,
                )
            )
            results.append(self._damage_result(move, damage))
        return tuple(results)

    def _status_result(self, move: Move) -> MoveMatchupResult:
        return MoveMatchupResult(
            move_id=move.id,
            priority=move.priority,
            accuracy=move.accuracy,
            minimum_damage=0,
            maximum_damage=0,
            minimum_percent=0.0,
            maximum_percent=0.0,
            ohko_chance=0.0,
            two_hko_chance=None,
            expected_damage=0.0,
            expected_damage_percent=0.0,
            classification="status_move",
            is_immune=False,
            is_status_move=True,
            requires_context=move.id in SPECIAL_CONTEXT_MOVES,
            missing_context=SPECIAL_CONTEXT_MOVES.get(move.id, ()),
        )

    def _damage_result(self, move: Move, damage) -> MoveMatchupResult:
        is_immune = damage.maximum_damage == 0
        expected_damage = calculate_expected_damage(damage.damage_rolls, move.accuracy)
        expected_percent = (
            round((expected_damage / damage.defender_max_hp) * 100, 1)
            if damage.defender_max_hp
            else 0.0
        )
        return MoveMatchupResult(
            move_id=move.id,
            priority=move.priority,
            accuracy=move.accuracy,
            minimum_damage=damage.minimum_damage,
            maximum_damage=damage.maximum_damage,
            minimum_percent=damage.minimum_percent,
            maximum_percent=damage.maximum_percent,
            ohko_chance=damage.ohko_chance,
            two_hko_chance=calculate_two_hko_chance(damage.damage_rolls, damage.defender_max_hp),
            expected_damage=expected_damage,
            expected_damage_percent=expected_percent,
            classification=classify_move_damage(
                damage.minimum_percent,
                damage.maximum_percent,
                is_status_move=False,
                is_immune=is_immune,
            ),
            is_immune=is_immune,
            is_status_move=False,
            requires_context=move.id in SPECIAL_CONTEXT_MOVES,
            missing_context=SPECIAL_CONTEXT_MOVES.get(move.id, ()),
        )
