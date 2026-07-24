from __future__ import annotations

from pokebrain.analysis.models import RecoveryAnalysis
from pokebrain.team.models import Team


RELIABLE = {"recover", "roost", "slackoff", "softboiled", "milkdrink", "shoreup"}
CONDITIONAL = {"synthesis", "morningsun", "moonlight"}
DRAINING = {"drainpunch", "gigadrain", "bitterblade", "drainingkiss", "hornleech"}
PASSIVE_ITEMS = {"leftovers", "blacksludge"}
PASSIVE_ABILITIES = {"poisonheal", "regenerator", "icebody", "raindish"}


class RecoveryAnalyzer:
    def analyze(self, team: Team) -> RecoveryAnalysis:
        reliable: list[str] = []
        conditional: list[str] = []
        draining: list[str] = []
        passive: list[str] = []

        for member in team.members:
            if any(move in RELIABLE for move in member.moves):
                reliable.append(member.species_id)
            if any(move in CONDITIONAL for move in member.moves):
                conditional.append(member.species_id)
            if any(move in DRAINING for move in member.moves):
                draining.append(member.species_id)
            if member.item_id in PASSIVE_ITEMS or member.ability_id in PASSIVE_ABILITIES:
                passive.append(member.species_id)

        return RecoveryAnalysis(
            reliable=tuple(reliable),
            conditional=tuple(conditional),
            draining=tuple(draining),
            passive=tuple(passive),
        )

