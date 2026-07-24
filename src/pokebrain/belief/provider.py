from __future__ import annotations

from contextlib import closing

from pokebrain.belief.distribution import ensure_uncertainty_floor, normalize
from pokebrain.belief.models import UNKNOWN_VALUE, BeliefState, PokemonBelief, WeightedValue
from pokebrain.battle.models import BattleState
from pokebrain.data.connection import connect
from pokebrain.data.manager import DataManager


DEFAULT_ITEMS = (
    WeightedValue("heavydutyboots", 0.22),
    WeightedValue("leftovers", 0.18),
    WeightedValue("choicescarf", 0.12),
    WeightedValue("choicespecs", 0.10),
    WeightedValue("choiceband", 0.10),
    WeightedValue(UNKNOWN_VALUE, 0.28),
)
DEFAULT_TERA_TYPES = (
    WeightedValue("Water", 0.16),
    WeightedValue("Fairy", 0.14),
    WeightedValue("Steel", 0.12),
    WeightedValue("Fire", 0.10),
    WeightedValue(UNKNOWN_VALUE, 0.48),
)


class LocalUsageBeliefProvider:
    def __init__(self, data_manager: DataManager | None = None) -> None:
        self.data_manager = data_manager or DataManager()
        self._move_distribution_cache: dict[tuple[str, int], tuple[WeightedValue[str], ...]] = {}

    def initial_belief(self, observed_state: BattleState) -> BeliefState:
        return BeliefState(
            opponent_team=tuple(
                self.belief_for_species(
                    species_id=member.species_id,
                    format_id=observed_state.format_id,
                    generation=observed_state.generation,
                    observed_moves=member.moves,
                    observed_item=member.item_id,
                    observed_ability=member.ability_id,
                    observed_tera_type=member.tera_type,
                )
                for member in observed_state.opponent.team
            )
        )

    def belief_for_species(
        self,
        *,
        species_id: str,
        format_id: str,
        generation: int,
        observed_moves: tuple[str, ...] = (),
        observed_item: str | None = None,
        observed_ability: str | None = None,
        observed_tera_type: str | None = None,
    ) -> PokemonBelief:
        species = self.data_manager.species.get_by_id(species_id)
        abilities = tuple(
            WeightedValue(ability_id, 1 / len(species.abilities))
            for ability_id in sorted(set(species.abilities.values()))
        ) if species and species.abilities else (WeightedValue(UNKNOWN_VALUE, 1.0),)
        moves = self._move_distribution(species_id, generation, observed_moves)
        return PokemonBelief(
            species_id=species_id,
            possible_items=(WeightedValue(observed_item, 1.0),) if observed_item else ensure_uncertainty_floor(DEFAULT_ITEMS),
            possible_abilities=(WeightedValue(observed_ability, 1.0),) if observed_ability else ensure_uncertainty_floor(abilities),
            possible_moves=moves,
            possible_tera_types=(WeightedValue(observed_tera_type, 1.0),) if observed_tera_type else ensure_uncertainty_floor(DEFAULT_TERA_TYPES),
            revealed_item=observed_item,
            revealed_ability=observed_ability,
            revealed_moves=frozenset(move for move in observed_moves if move),
            revealed_tera_type=observed_tera_type,
        )

    def _move_distribution(self, species_id: str, generation: int, observed_moves: tuple[str, ...]) -> tuple[WeightedValue[str], ...]:
        if observed_moves:
            return normalize(tuple(WeightedValue(move, 1.0) for move in observed_moves))
        cache_key = (species_id, generation)
        cached = self._move_distribution_cache.get(cache_key)
        if cached is not None:
            return cached
        with closing(connect(self.data_manager.database_path)) as connection:
            rows = connection.execute(
                """
                SELECT move_id
                FROM learnsets
                WHERE species_id = ? AND generation <= ?
                ORDER BY move_id
                LIMIT 24
                """,
                (species_id, generation),
            ).fetchall()
        if not rows:
            result = (WeightedValue(UNKNOWN_VALUE, 1.0),)
            self._move_distribution_cache[cache_key] = result
            return result
        selected = tuple(row["move_id"] for row in rows[:12])
        probability = 0.9 / len(selected)
        result = normalize(tuple(WeightedValue(move_id, probability) for move_id in selected) + (WeightedValue(UNKNOWN_VALUE, 0.1),))
        self._move_distribution_cache[cache_key] = result
        return result
