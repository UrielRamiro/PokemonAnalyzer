from __future__ import annotations

from pokebrain.replays.public_models import ParsedPublicReplay, PartialPolicyExample, PublicPokemonState
from pokebrain.replays.recovery_models import (
    AuthoritativeMoveSet,
    EvidenceConfidence,
    EvidenceConflict,
    EvidenceSource,
    EvidenceValue,
    PublicKnowledge,
    ReplayArtifactBundle,
    ResolvedPokemon,
    ResolvedTeam,
    TeamResolutionResult,
)
from pokebrain.team.models import Team
from pokebrain.team.parser import TeamParser


class TeamEvidenceResolver:
    def resolve(
        self,
        replay: ParsedPublicReplay,
        partial_examples: tuple[PartialPolicyExample, ...],
        artifacts: ReplayArtifactBundle,
    ) -> TeamResolutionResult:
        unresolved: list[str] = []
        conflicts: list[EvidenceConflict] = []
        player_1 = self._team_from_export("p1", replay.format_id, artifacts.player_1_team_export, unresolved)
        player_2 = self._team_from_export("p2", replay.format_id, artifacts.player_2_team_export, unresolved)
        public_state = partial_examples[0].observed_state if partial_examples else (replay.snapshots[0].state if replay.snapshots else None)
        if public_state is not None:
            if player_1 is not None:
                conflicts.extend(_conflicts_with_public(replay.replay_id, player_1, tuple(_side_pokemon(public_state, "p1"))))
            if player_2 is not None:
                conflicts.extend(_conflicts_with_public(replay.replay_id, player_2, tuple(_side_pokemon(public_state, "p2"))))
        if player_1 is None:
            unresolved.append("missing_player_1_team")
        if player_2 is None:
            unresolved.append("missing_player_2_team")
        return TeamResolutionResult(
            player_1_team=player_1,
            player_2_team=player_2,
            unresolved_reasons=tuple(dict.fromkeys(unresolved)),
            conflicts=tuple(conflicts),
        )

    def public_knowledge(self, side: str, state) -> PublicKnowledge:
        moves = []
        items = []
        abilities = []
        for pokemon in _side_pokemon(state, side):
            for move in sorted(pokemon.revealed_moves):
                moves.append(EvidenceValue(move, EvidenceSource.PUBLIC_REPLAY_LOG, EvidenceConfidence.OBSERVED, state.turn))
            if pokemon.revealed_item:
                items.append(EvidenceValue(pokemon.revealed_item, EvidenceSource.PUBLIC_REPLAY_LOG, EvidenceConfidence.OBSERVED, state.turn))
            if pokemon.revealed_ability:
                abilities.append(EvidenceValue(pokemon.revealed_ability, EvidenceSource.PUBLIC_REPLAY_LOG, EvidenceConfidence.OBSERVED, state.turn))
        return PublicKnowledge(side=side, revealed_moves=tuple(moves), revealed_items=tuple(items), revealed_abilities=tuple(abilities))

    def _team_from_export(
        self,
        side: str,
        format_id: str,
        team_export: str | None,
        unresolved: list[str],
    ) -> ResolvedTeam | None:
        if not team_export:
            return None
        parsed = TeamParser().parse(format_id, team_export)
        if parsed.team is None:
            unresolved.extend(parsed.parse_errors or (f"{side}_team_export_unparseable",))
            return None
        return _resolved_team(side, parsed.team, EvidenceSource.TEAM_EXPORT, EvidenceConfidence.AUTHORITATIVE)


def _resolved_team(
    side: str,
    team: Team,
    source: EvidenceSource,
    confidence: EvidenceConfidence,
) -> ResolvedTeam:
    members = tuple(
        ResolvedPokemon(
            set_data=member,
            species=EvidenceValue(member.species_id, source, confidence, None),
            moves=EvidenceValue(AuthoritativeMoveSet(member.moves), source, confidence, None),
            item=EvidenceValue(member.item_id, source, confidence, None),
            ability=EvidenceValue(member.ability_id, source, confidence, None),
            tera_type=EvidenceValue(member.tera_type, source, confidence, None),
        )
        for member in team.members
    )
    return ResolvedTeam(side=side, team=team, members=members, source=source)


def _conflicts_with_public(
    replay_id: str,
    team: ResolvedTeam,
    public_pokemon: tuple[PublicPokemonState, ...],
) -> tuple[EvidenceConflict, ...]:
    conflicts: list[EvidenceConflict] = []
    for public in public_pokemon:
        resolved = next((member for member in team.members if member.set_data.species_id == public.species_id), None)
        if resolved is None:
            continue
        if public.revealed_item and resolved.set_data.item_id and public.revealed_item != resolved.set_data.item_id:
            conflicts.append(EvidenceConflict("item", resolved.set_data.item_id, public.revealed_item, replay_id, None))
        if public.revealed_ability and resolved.set_data.ability_id and public.revealed_ability != resolved.set_data.ability_id:
            conflicts.append(EvidenceConflict("ability", resolved.set_data.ability_id, public.revealed_ability, replay_id, None))
        for move in public.revealed_moves:
            if move not in resolved.set_data.moves:
                conflicts.append(EvidenceConflict("move", resolved.set_data.moves, move, replay_id, None))
    return tuple(conflicts)


def _side_pokemon(state, side: str):
    public_side = next((candidate for candidate in state.sides if candidate.side == side), None)
    return public_side.pokemon if public_side else ()
