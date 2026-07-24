from __future__ import annotations

from pokebrain.analysis.models import RemovalAnalysis, RemovalMoveUse
from pokebrain.team.models import Team


REMOVAL_EFFECTS = {
    "rapidspin": "removes hazards from own side",
    "defog": "removes hazards from both sides",
    "mortalspin": "removes hazards from own side and poisons foes",
    "tidyup": "removes hazards/substitutes and boosts user",
    "courtchange": "swaps side conditions",
}


class RemovalAnalyzer:
    def analyze(self, team: Team) -> RemovalAnalysis:
        removers: list[RemovalMoveUse] = []
        for member in team.members:
            for move_id in member.moves:
                if move_id in REMOVAL_EFFECTS:
                    removers.append(
                        RemovalMoveUse(
                            species_id=member.species_id,
                            move_id=move_id,
                            effect=REMOVAL_EFFECTS[move_id],
                        )
                    )
        return RemovalAnalysis(removers=tuple(removers))

