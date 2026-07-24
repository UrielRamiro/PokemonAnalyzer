from __future__ import annotations

from pokebrain.analysis.models import HazardAnalysis
from pokebrain.team.models import Team


class HazardAnalyzer:
    def analyze(self, team: Team) -> HazardAnalysis:
        return HazardAnalysis(
            stealth_rock_users=self._users(team, "stealthrock"),
            spikes_users=self._users(team, "spikes"),
            toxic_spikes_users=self._users(team, "toxicspikes"),
            sticky_web_users=self._users(team, "stickyweb"),
        )

    def _users(self, team: Team, move_id: str) -> tuple[str, ...]:
        return tuple(member.species_id for member in team.members if move_id in member.moves)

