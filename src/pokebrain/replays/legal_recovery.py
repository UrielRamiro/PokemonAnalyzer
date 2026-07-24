from __future__ import annotations

from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.battle.models import ActivePokemonState, BattleAction, BattleSideState
from pokebrain.replays.public_models import PublicReplayState
from pokebrain.replays.recovery_models import (
    AuthoritativeMoveSet,
    EvidenceSource,
    HypothesizedMoveSet,
    LegalActionQuality,
    LegalActionSet,
    ResolvedTeam,
)
from pokebrain.team.models import PokemonSet


class RecoveredLegalActionGenerator:
    def generate(
        self,
        *,
        state: PublicReplayState,
        actor_side: str,
        actor_team: ResolvedTeam | None,
        authoritative_actions: tuple[BattleAction, ...] | None = None,
        forced_switch: bool = False,
    ) -> LegalActionSet:
        if authoritative_actions is not None:
            return LegalActionSet(
                actions=authoritative_actions,
                quality=LegalActionQuality.AUTHORITATIVE,
                evidence_sources=(EvidenceSource.AUTHORITATIVE_RUNNER,),
                missing_constraints=(),
            )
        if actor_team is None:
            return LegalActionSet((), LegalActionQuality.UNAVAILABLE, (), ("missing_actor_team",))
        if any(isinstance(member.moves.value, HypothesizedMoveSet) for member in actor_team.members):
            return LegalActionSet((), LegalActionQuality.UNAVAILABLE, (EvidenceSource.STATISTICAL_INFERENCE,), ("hypothesized_moveset_not_allowed",))
        active_public = _active_public_pokemon(state, actor_side)
        if active_public is None or active_public.species_id is None:
            return LegalActionSet((), LegalActionQuality.UNAVAILABLE, (actor_team.source,), ("missing_active_pokemon",))
        active_set = next((member.set_data for member in actor_team.members if member.set_data.species_id == active_public.species_id), None)
        if active_set is None:
            return LegalActionSet((), LegalActionQuality.UNAVAILABLE, (actor_team.source,), ("active_pokemon_not_in_team",))
        battle_side = BattleSideState(
            active=ActivePokemonState(set_data=active_set, current_hp=_public_hp(active_public), trapped=active_public.active and getattr(active_public, "trapped", False)),
            team=tuple(member.set_data for member in actor_team.members),
            fainted_ids=tuple(pokemon.species_id for pokemon in _side_pokemon(state, actor_side) if pokemon.fainted and pokemon.species_id),
        )
        actions = LegalActionGenerator().generate_for_side(battle_side)
        if forced_switch:
            actions = tuple(action for action in actions if action.switch_target_id)
        actions, lock_missing = _apply_basic_locks(actions, active_set, active_public.revealed_moves)
        return LegalActionSet(
            actions=actions,
            quality=LegalActionQuality.RECONSTRUCTED_PARTIAL if lock_missing else LegalActionQuality.RECONSTRUCTED_COMPLETE,
            evidence_sources=(actor_team.source,),
            missing_constraints=("choice_lock",) if lock_missing else (),
        )


def _apply_basic_locks(
    actions: tuple[BattleAction, ...],
    active_set: PokemonSet,
    revealed_moves: frozenset[str],
) -> tuple[tuple[BattleAction, ...], bool]:
    if active_set.item_id not in {"choiceband", "choicescarf", "choicespecs"}:
        return actions, False
    if len(revealed_moves) == 1:
        locked_move = next(iter(revealed_moves))
        return tuple(action for action in actions if action.switch_target_id or action.move_id == locked_move), False
    return actions, True


def _active_public_pokemon(state: PublicReplayState, side: str):
    return next((pokemon for pokemon in _side_pokemon(state, side) if pokemon.active), None)


def _side_pokemon(state: PublicReplayState, side: str):
    public_side = next((candidate for candidate in state.sides if candidate.side == side), None)
    return public_side.pokemon if public_side else ()


def _public_hp(pokemon) -> int:
    if pokemon.hp_current is not None:
        return pokemon.hp_current
    if pokemon.hp_fraction is not None:
        return max(0, int(round(pokemon.hp_fraction * 100)))
    return 100
