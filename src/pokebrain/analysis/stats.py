from __future__ import annotations

from pokebrain.analysis.models import CalculatedStats
from pokebrain.data.models import PokemonSpecies
from pokebrain.team.models import PokemonSet
from pokebrain.team.stat_system import effective_ivs_for_format, stat_investment_for_formula


NATURES = {
    "Adamant": ("attack", "special_attack"),
    "Bold": ("defense", "attack"),
    "Calm": ("special_defense", "attack"),
    "Careful": ("special_defense", "special_attack"),
    "Impish": ("defense", "special_attack"),
    "Jolly": ("speed", "special_attack"),
    "Modest": ("special_attack", "attack"),
    "Timid": ("speed", "attack"),
}


class StatCalculator:
    def calculate(self, pokemon_set: PokemonSet, species: PokemonSpecies, format_id: str | None = None) -> CalculatedStats:
        level = pokemon_set.level
        evs = pokemon_set.evs
        ivs = effective_ivs_for_format(pokemon_set.ivs, format_id)
        return CalculatedStats(
            hp=self._hp(species.base_stats.hp, stat_investment_for_formula(evs.hp, format_id), level, ivs.hp),
            attack=self._other("attack", species.base_stats.attack, stat_investment_for_formula(evs.attack, format_id), level, pokemon_set.nature, ivs.attack),
            defense=self._other("defense", species.base_stats.defense, stat_investment_for_formula(evs.defense, format_id), level, pokemon_set.nature, ivs.defense),
            special_attack=self._other(
                "special_attack",
                species.base_stats.special_attack,
                stat_investment_for_formula(evs.special_attack, format_id),
                level,
                pokemon_set.nature,
                ivs.special_attack,
            ),
            special_defense=self._other(
                "special_defense",
                species.base_stats.special_defense,
                stat_investment_for_formula(evs.special_defense, format_id),
                level,
                pokemon_set.nature,
                ivs.special_defense,
            ),
            speed=self._other("speed", species.base_stats.speed, stat_investment_for_formula(evs.speed, format_id), level, pokemon_set.nature, ivs.speed),
        )

    def _hp(self, base: int, stat_investment: int, level: int, iv: int = 31) -> int:
        return ((2 * base + iv + stat_investment) * level) // 100 + level + 10

    def _other(
        self,
        stat_name: str,
        base: int,
        stat_investment: int,
        level: int,
        nature: str | None,
        iv: int = 31,
    ) -> int:
        value = ((2 * base + iv + stat_investment) * level) // 100 + 5
        increased, decreased = NATURES.get(nature or "", ("", ""))
        if stat_name == increased:
            value = int(value * 1.1)
        elif stat_name == decreased:
            value = int(value * 0.9)
        return value
