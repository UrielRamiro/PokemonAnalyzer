from __future__ import annotations

from pokebrain.analysis.type_chart import type_multiplier
from pokebrain.data.manager import DataManager
from pokebrain.team.models import PokemonSet


def stealth_rock_percent(pokemon_set: PokemonSet, data_manager: DataManager) -> float:
    if pokemon_set.item_id == "heavydutyboots":
        return 0.0
    species = data_manager.species.get_by_id(pokemon_set.species_id)
    if species is None:
        return 0.0
    return 12.5 * type_multiplier("Rock", species.types)

