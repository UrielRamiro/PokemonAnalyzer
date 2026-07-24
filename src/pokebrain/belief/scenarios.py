from __future__ import annotations

from dataclasses import replace
from itertools import product

from pokebrain.battle.models import ActivePokemonState, BattleSideState, BattleState
from pokebrain.belief.distribution import normalize
from pokebrain.belief.models import BeliefSearchConfig, BeliefState, OpponentScenario, PokemonBelief, UNKNOWN_VALUE, WeightedValue
from pokebrain.team.models import PokemonSet


class OpponentScenarioGenerator:
    def generate(
        self,
        observed_state: BattleState,
        belief_state: BeliefState,
        config: BeliefSearchConfig | None = None,
    ) -> tuple[OpponentScenario, ...]:
        config = config or BeliefSearchConfig()
        active_id = observed_state.opponent.active.set_data.species_id
        belief = next((item for item in belief_state.opponent_team if item.species_id == active_id), None)
        if belief is None:
            return (OpponentScenario(1.0, observed_state, ("No active opponent belief available.",)),)
        candidates = sorted(
            self._active_scenarios(observed_state, belief),
            key=lambda item: item.probability,
            reverse=True,
        )
        filtered = tuple(item for item in candidates if item.probability >= config.minimum_probability)
        selected = filtered[: config.maximum_scenarios] if filtered else tuple(candidates[: config.maximum_scenarios])
        total = sum(item.probability for item in selected)
        if total <= 0:
            return (OpponentScenario(1.0, observed_state, ("Inconsistent belief fallback.",)),)
        return tuple(replace(item, probability=item.probability / total) for item in selected)

    def _active_scenarios(self, state: BattleState, belief: PokemonBelief) -> tuple[OpponentScenario, ...]:
        items = _top_values(belief.possible_items, 3)
        abilities = _top_values(belief.possible_abilities, 2)
        teras = _top_values(belief.possible_tera_types, 2)
        move_sets = _move_sets(belief)
        scenarios: list[OpponentScenario] = []
        for item, ability, tera, moves in product(items, abilities, teras, move_sets):
            probability = item.probability * ability.probability * tera.probability * moves.probability
            resolved = self._resolve_state(state, item.value, ability.value, tera.value, moves.value)
            assumptions = tuple(
                assumption
                for assumption in (
                    f"item={item.value}" if item.value != UNKNOWN_VALUE else None,
                    f"ability={ability.value}" if ability.value != UNKNOWN_VALUE else None,
                    f"tera={tera.value}" if tera.value != UNKNOWN_VALUE else None,
                    f"moves={','.join(moves.value)}",
                )
                if assumption is not None
            )
            scenarios.append(OpponentScenario(probability=probability, resolved_state=resolved, assumptions=assumptions))
        return tuple(scenarios)

    def _resolve_state(
        self,
        state: BattleState,
        item_id: str,
        ability_id: str,
        tera_type: str,
        moves: tuple[str, ...],
    ) -> BattleState:
        active = state.opponent.active.set_data
        resolved_set = replace(
            active,
            item_id=None if item_id == UNKNOWN_VALUE else item_id,
            ability_id=None if ability_id == UNKNOWN_VALUE else ability_id,
            tera_type=None if tera_type == UNKNOWN_VALUE else tera_type,
            moves=moves or active.moves,
        )
        resolved_active = replace(state.opponent.active, set_data=resolved_set)
        resolved_team = tuple(
            resolved_set if member.species_id == resolved_set.species_id else member
            for member in state.opponent.team
        )
        return replace(state, opponent=replace(state.opponent, active=resolved_active, team=resolved_team))


def _top_values(values: tuple[WeightedValue[str], ...], count: int) -> tuple[WeightedValue[str], ...]:
    normalized = normalize(values)
    return tuple(sorted(normalized, key=lambda item: item.probability, reverse=True)[:count])


def _move_sets(belief: PokemonBelief) -> tuple[WeightedValue[tuple[str, ...]], ...]:
    revealed = tuple(sorted(belief.revealed_moves))
    candidates = [item for item in sorted(belief.possible_moves, key=lambda item: item.probability, reverse=True) if item.value != UNKNOWN_VALUE]
    if not candidates and revealed:
        return (WeightedValue(revealed, 1.0),)
    if not candidates:
        return (WeightedValue(tuple(), 1.0),)
    move_set = tuple(dict.fromkeys((*revealed, *(item.value for item in candidates))) )[:4]
    probability = sum(item.probability for item in candidates if item.value in move_set)
    return (WeightedValue(move_set, probability or 1.0),)
