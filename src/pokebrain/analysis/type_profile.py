from __future__ import annotations

from pokebrain.analysis.defensive_modifiers import DefensiveModifier
from pokebrain.analysis.models import (
    PokemonTypeProfile,
    TeamTypeProfile,
    TeamTypeSummary,
    TypeMatchup,
)
from pokebrain.analysis.type_chart import TYPES, type_multiplier
from pokebrain.data.manager import DataManager
from pokebrain.team.models import Team


class TypeProfileAnalyzer:
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
        self.modifier = DefensiveModifier()

    def analyze(self, team: Team) -> TeamTypeProfile:
        members: list[PokemonTypeProfile] = []

        for member in team.members:
            species = self.data_manager.species.get_by_id(member.species_id)
            if species is None:
                continue
            matchups = []
            for attacking_type in TYPES:
                base = type_multiplier(attacking_type, species.types)
                adjusted = self.modifier.apply(member, attacking_type, base)
                matchups.append(TypeMatchup(attacking_type=attacking_type, multiplier=adjusted))
            members.append(PokemonTypeProfile(species_id=member.species_id, matchups=tuple(matchups)))

        summary = []
        for attacking_type in TYPES:
            multipliers = [
                matchup.multiplier
                for member in members
                for matchup in member.matchups
                if matchup.attacking_type == attacking_type
            ]
            summary.append(
                TeamTypeSummary(
                    attacking_type=attacking_type,
                    weaknesses=sum(1 for value in multipliers if value > 1),
                    quad_weaknesses=sum(1 for value in multipliers if value >= 4),
                    resistances=sum(1 for value in multipliers if 0 < value < 1),
                    immunities=sum(1 for value in multipliers if value == 0),
                )
            )

        return TeamTypeProfile(members=tuple(members), summary=tuple(summary))

