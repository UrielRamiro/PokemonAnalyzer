from __future__ import annotations

from pokebrain.analysis.hazards import HazardAnalyzer
from pokebrain.analysis.models import TeamAnalysis
from pokebrain.analysis.recovery import RecoveryAnalyzer
from pokebrain.analysis.removal import RemovalAnalyzer
from pokebrain.analysis.roles import RoleAnalyzer
from pokebrain.analysis.speed_control import SpeedControlAnalyzer
from pokebrain.analysis.type_profile import TypeProfileAnalyzer
from pokebrain.data.manager import DataManager
from pokebrain.showdown import ShowdownEngine
from pokebrain.team.parser import TeamParser


class TeamAnalyzer:
    def __init__(
        self,
        data_manager: DataManager | None = None,
        showdown_engine: ShowdownEngine | None = None,
    ) -> None:
        self.data_manager = data_manager or DataManager()
        self.showdown_engine = showdown_engine or ShowdownEngine()
        self.parser = TeamParser()

    def analyze(self, format_id: str, team_text: str) -> TeamAnalysis:
        parsed = self.parser.parse(format_id, team_text)
        validation = self.showdown_engine.validate_team(format_id, team_text)

        if parsed.team is None:
            empty_team = TeamParser().parse(format_id, "").team
            raise ValueError("Team text did not contain any parseable members.")

        team = parsed.team
        hazards = HazardAnalyzer().analyze(team)
        removal = RemovalAnalyzer().analyze(team)
        type_profile = TypeProfileAnalyzer(self.data_manager).analyze(team)
        speed_profile = SpeedControlAnalyzer(self.data_manager).analyze(team)
        recovery = RecoveryAnalyzer().analyze(team)
        roles = RoleAnalyzer(self.data_manager).analyze(team)

        return TeamAnalysis(
            format_id=format_id,
            validation=validation,
            parse_errors=parsed.parse_errors,
            member_count=len(team.members),
            hazards=hazards,
            removal=removal,
            type_profile=type_profile,
            speed_profile=speed_profile,
            recovery=recovery,
            roles=roles,
            warnings=self._warnings(recovery, removal),
        )

    def _warnings(self, recovery, removal) -> tuple[str, ...]:
        warnings: list[str] = []
        if not recovery.reliable:
            warnings.append("No reliable recovery detected.")
        if not removal.removers:
            warnings.append("No hazard removal detected.")
        return tuple(warnings)

