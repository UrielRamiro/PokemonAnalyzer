from __future__ import annotations

from pokebrain.team.models import PokemonSet


class DefensiveModifier:
    def apply(
        self,
        pokemon_set: PokemonSet,
        attacking_type: str,
        base_multiplier: float,
    ) -> float:
        ability = pokemon_set.ability_id

        if ability == "levitate" and attacking_type == "Ground":
            return 0.0
        if ability == "flashfire" and attacking_type == "Fire":
            return 0.0
        if ability in {"waterabsorb", "stormdrain"} and attacking_type == "Water":
            return 0.0
        if ability == "voltabsorb" and attacking_type == "Electric":
            return 0.0
        if ability == "thickfat" and attacking_type in {"Fire", "Ice"}:
            return base_multiplier * 0.5
        if ability == "dryskin" and attacking_type == "Water":
            return 0.0
        if ability == "dryskin" and attacking_type == "Fire":
            return base_multiplier * 1.25

        return base_multiplier

