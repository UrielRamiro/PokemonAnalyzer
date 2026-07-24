from __future__ import annotations

from pokebrain.analysis.models import PriorityMoveUse, SpeedEntry, SpeedProfile
from pokebrain.analysis.stats import StatCalculator
from pokebrain.data.manager import DataManager
from pokebrain.team.models import Team


class SpeedControlAnalyzer:
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager
        self.stat_calculator = StatCalculator()

    def analyze(self, team: Team) -> SpeedProfile:
        entries: list[SpeedEntry] = []
        priority: list[PriorityMoveUse] = []

        for member in team.members:
            species = self.data_manager.species.get_by_id(member.species_id)
            if species is not None:
                stats = self.stat_calculator.calculate(member, species, team.format_id)
                entries.append(SpeedEntry(species_id=member.species_id, speed=stats.speed))

            for move_id in member.moves:
                move = self.data_manager.moves.get_by_id(move_id)
                if move is not None and move.priority > 0:
                    priority.append(
                        PriorityMoveUse(
                            species_id=member.species_id,
                            move_id=move_id,
                            priority=move.priority,
                        )
                    )

        return SpeedProfile(
            entries=tuple(sorted(entries, key=lambda entry: entry.speed, reverse=True)),
            priority=tuple(priority),
        )
