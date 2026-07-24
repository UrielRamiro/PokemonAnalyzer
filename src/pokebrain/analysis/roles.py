from __future__ import annotations

from pokebrain.analysis.hazards import HazardAnalyzer
from pokebrain.analysis.models import RoleAssignment
from pokebrain.analysis.removal import REMOVAL_EFFECTS
from pokebrain.data.manager import DataManager
from pokebrain.team.models import PokemonSet, Team


CHOICE_ITEMS = {"choiceband", "choicespecs", "choicescarf"}
SETUP_MOVES = {"swordsdance", "nastyplot", "dragondance", "calmmind", "bulkup", "quiverdance"}
PIVOT_MOVES = {"uturn", "voltswitch", "flipturn", "partingshot", "teleport"}
CLERIC_MOVES = {"healbell", "aromatherapy", "healingwish"}
TRAPPING = {"magnetpull", "shadowtag", "arenatrap", "jawlock", "spiritshackle", "thousandwaves"}


class RoleAnalyzer:
    def __init__(self, data_manager: DataManager) -> None:
        self.data_manager = data_manager

    def analyze(self, team: Team) -> tuple[RoleAssignment, ...]:
        assignments: list[RoleAssignment] = []
        for member in team.members:
            roles: list[str] = []
            evidence: list[str] = []
            self._hazards(member, roles, evidence)
            self._removal(member, roles, evidence)
            self._choice(member, roles, evidence)
            self._setup(member, roles, evidence)
            self._pivot(member, roles, evidence)
            self._cleric(member, roles, evidence)
            self._trapper(member, roles, evidence)
            self._physical_tank(member, roles, evidence)
            assignments.append(
                RoleAssignment(
                    species_id=member.species_id,
                    roles=tuple(roles),
                    evidence=tuple(evidence),
                )
            )
        return tuple(assignments)

    def _hazards(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        hazards = {"stealthrock", "spikes", "toxicspikes", "stickyweb"}
        found = hazards.intersection(member.moves)
        if found:
            roles.append("hazard_setter")
            evidence.append(f"hazard moves: {', '.join(sorted(found))}")

    def _removal(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        found = set(REMOVAL_EFFECTS).intersection(member.moves)
        if found:
            roles.append("hazard_remover")
            evidence.append(f"removal moves: {', '.join(sorted(found))}")

    def _choice(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        if member.item_id in CHOICE_ITEMS:
            roles.append("choice_attacker")
            evidence.append(f"item: {member.item_id}")

    def _setup(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        found = SETUP_MOVES.intersection(member.moves)
        if found:
            roles.append("setup_sweeper")
            evidence.append(f"setup moves: {', '.join(sorted(found))}")

    def _pivot(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        found = PIVOT_MOVES.intersection(member.moves)
        if found:
            roles.append("pivot")
            evidence.append(f"pivot moves: {', '.join(sorted(found))}")

    def _cleric(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        found = CLERIC_MOVES.intersection(member.moves)
        if found:
            roles.append("cleric")
            evidence.append(f"support moves: {', '.join(sorted(found))}")

    def _trapper(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        found = TRAPPING.intersection(member.moves)
        if member.ability_id in TRAPPING or found:
            roles.append("trapper")
            evidence.append(f"trapping: {member.ability_id or ', '.join(sorted(found))}")

    def _physical_tank(self, member: PokemonSet, roles: list[str], evidence: list[str]) -> None:
        species = self.data_manager.species.get_by_id(member.species_id)
        if species and member.evs.hp >= 200 and species.base_stats.defense >= 110:
            roles.append("physical_tank")
            evidence.append(
                f"{member.evs.hp} HP EVs + {species.base_stats.defense} base Defense"
            )

