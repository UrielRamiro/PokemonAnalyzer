from __future__ import annotations

from pokebrain.analysis.matchup.ko_classifier import calculate_ko_range, move_score
from pokebrain.analysis.matchup.models import (
    CandidateAction,
    MatchupAnalysis,
    MatchupSide,
    MatchupVerdict,
    TurnOrder,
)
from pokebrain.analysis.matchup.move_evaluator import MoveMatchupEvaluator
from pokebrain.analysis.matchup.speed_evaluator import compare_turn_order
from pokebrain.analysis.stats import StatCalculator
from pokebrain.damage import FieldState, ShowdownDamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.team.models import PokemonSet


class MatchupAnalyzer:
    def __init__(
        self,
        data_manager: DataManager | None = None,
        move_evaluator: MoveMatchupEvaluator | None = None,
        stat_calculator: StatCalculator | None = None,
    ) -> None:
        self.data_manager = data_manager or DataManager()
        self.move_evaluator = move_evaluator or MoveMatchupEvaluator(
            damage_engine=ShowdownDamageEngine(),
            data_manager=self.data_manager,
        )
        self.stat_calculator = stat_calculator or StatCalculator()

    def compare(
        self,
        generation: int,
        pokemon_a: PokemonSet,
        pokemon_b: PokemonSet,
        field: FieldState | None = None,
        format_id: str = "unknown",
    ) -> MatchupAnalysis:
        field = field or FieldState()
        species_a = self.data_manager.species.get_by_id(pokemon_a.species_id)
        species_b = self.data_manager.species.get_by_id(pokemon_b.species_id)
        if species_a is None or species_b is None:
            raise ValueError("Both Pokemon must exist in the local database.")

        stats_a = self.stat_calculator.calculate(pokemon_a, species_a, format_id)
        stats_b = self.stat_calculator.calculate(pokemon_b, species_b, format_id)
        moves_a = self.move_evaluator.evaluate_moves(generation, pokemon_a, pokemon_b, field, format_id)
        moves_b = self.move_evaluator.evaluate_moves(generation, pokemon_b, pokemon_a, field, format_id)

        side_a = self._build_side(pokemon_a, stats_a.speed, moves_a, stats_b.hp)
        side_b = self._build_side(pokemon_b, stats_b.speed, moves_b, stats_a.hp)
        turn_order = self._turn_order(side_a, side_b)
        verdict = determine_verdict(side_a, side_b, turn_order)
        reasons = self._reasons(side_a, side_b, turn_order, verdict)
        limitations = self._limitations(side_a, side_b)

        return MatchupAnalysis(
            generation=generation,
            pokemon_a=side_a,
            pokemon_b=side_b,
            turn_order=turn_order,
            verdict=verdict,
            confidence=self._confidence(verdict, limitations),
            reasons=reasons,
            limitations=limitations,
        )

    def _build_side(
        self,
        pokemon: PokemonSet,
        speed: int,
        move_results,
        defender_hp: int,
    ) -> MatchupSide:
        offensive_moves = tuple(move for move in move_results if not move.is_status_move)
        best_move = max(offensive_moves, key=move_score, default=None)
        ko_range = (
            calculate_ko_range(best_move.minimum_damage, best_move.maximum_damage, defender_hp)
            if best_move is not None
            else None
        )
        return MatchupSide(
            pokemon_id=pokemon.species_id,
            calculated_speed=speed,
            move_results=tuple(move_results),
            best_move=best_move,
            fastest_ko_turns=ko_range.optimistic_turns if ko_range else None,
            ko_range=ko_range,
            has_guaranteed_ohko=any(move.minimum_percent >= 100 for move in offensive_moves),
            has_possible_ohko=any(move.maximum_percent >= 100 for move in offensive_moves),
        )

    def _turn_order(self, side_a: MatchupSide, side_b: MatchupSide) -> TurnOrder:
        if side_a.best_move is None or side_b.best_move is None:
            if side_a.calculated_speed > side_b.calculated_speed:
                return TurnOrder.A_FIRST
            if side_b.calculated_speed > side_a.calculated_speed:
                return TurnOrder.B_FIRST
            return TurnOrder.SPEED_TIE
        return compare_turn_order(
            CandidateAction(side_a.pokemon_id, side_a.best_move, side_a.calculated_speed),
            CandidateAction(side_b.pokemon_id, side_b.best_move, side_b.calculated_speed),
        )

    def _reasons(
        self,
        side_a: MatchupSide,
        side_b: MatchupSide,
        turn_order: TurnOrder,
        verdict: MatchupVerdict,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if turn_order is TurnOrder.A_FIRST:
            reasons.append(f"{side_a.pokemon_id} is expected to move first.")
        elif turn_order is TurnOrder.B_FIRST:
            reasons.append(f"{side_b.pokemon_id} is expected to move first.")
        else:
            reasons.append("Both sides have a speed tie with their selected moves.")

        for side in (side_a, side_b):
            if side.best_move:
                reasons.append(
                    f"{side.pokemon_id}'s best move is {side.best_move.move_id} "
                    f"({side.best_move.minimum_percent}-{side.best_move.maximum_percent}%)."
                )
                if side.best_move.ohko_chance:
                    reasons.append(
                        f"{side.best_move.move_id} has {side.best_move.ohko_chance:.1%} OHKO chance."
                    )
                if side.best_move.requires_context:
                    reasons.append(
                        f"{side.best_move.move_id} requires extra context: "
                        f"{', '.join(side.best_move.missing_context)}."
                    )

        reasons.append(f"Verdict rule selected: {verdict.value}.")
        return tuple(reasons)

    def _limitations(self, side_a: MatchupSide, side_b: MatchupSide) -> tuple[str, ...]:
        limitations = [
            "No switching considered.",
            "Both Pokemon are considered at full HP.",
            "No hazards, weather, terrain, status, boosts or Terastalization unless passed in the field/request.",
        ]
        for side in (side_a, side_b):
            if side.best_move and side.best_move.requires_context:
                limitations.append(
                    f"{side.best_move.move_id} is not fully modeled: "
                    f"{', '.join(side.best_move.missing_context)}."
                )
        return tuple(limitations)

    def _confidence(self, verdict: MatchupVerdict, limitations: tuple[str, ...]) -> float:
        if verdict is MatchupVerdict.UNCERTAIN:
            return 0.25
        return max(0.45, 0.8 - 0.05 * len(limitations))


def determine_verdict(
    side_a: MatchupSide,
    side_b: MatchupSide,
    turn_order: TurnOrder,
) -> MatchupVerdict:
    a_move = side_a.best_move
    b_move = side_b.best_move

    if a_move is None or b_move is None:
        return MatchupVerdict.UNCERTAIN

    if turn_order is TurnOrder.A_FIRST and a_move.minimum_percent >= 100:
        return MatchupVerdict.A_FAVORED
    if turn_order is TurnOrder.B_FIRST and b_move.minimum_percent >= 100:
        return MatchupVerdict.B_FAVORED
    if side_a.fastest_ko_turns is None:
        return MatchupVerdict.B_FAVORED
    if side_b.fastest_ko_turns is None:
        return MatchupVerdict.A_FAVORED
    if side_a.fastest_ko_turns < side_b.fastest_ko_turns:
        return MatchupVerdict.A_FAVORED
    if side_b.fastest_ko_turns < side_a.fastest_ko_turns:
        return MatchupVerdict.B_FAVORED
    return MatchupVerdict.EVEN
