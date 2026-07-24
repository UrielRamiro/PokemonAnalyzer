from __future__ import annotations

from dataclasses import replace

from pokebrain.replays.public_events import (
    AbilityRevealed,
    BattleEnded,
    BoostChanged,
    HpChanged,
    ItemConsumed,
    ItemRevealed,
    MoveUsed,
    PokemonFainted,
    PokemonPreviewed,
    PokemonSwitched,
    ReplayEvent,
    SideConditionEnded,
    SideConditionStarted,
    StatusApplied,
    StatusRemoved,
    TeraUsed,
    TerrainChanged,
    TurnStarted,
    UnsupportedReplayEvent,
    WeatherChanged,
)
from pokebrain.replays.public_models import (
    Boosts,
    FieldState,
    PublicPokemonState,
    PublicReplayState,
    PublicSideState,
    ReplayPokemonId,
    ReplayReconstructionStatus,
    ReplayStateInvariantError,
)
from pokebrain.utils import to_id


class PublicReplayStateReducer:
    def __init__(self, replay_id: str = "unknown") -> None:
        self.replay_id = replay_id

    def initial_state(self) -> PublicReplayState:
        return PublicReplayState(
            turn=0,
            sides=(PublicSideState("p1"), PublicSideState("p2")),
            field=FieldState(),
        )

    def apply(self, state: PublicReplayState, event: ReplayEvent) -> PublicReplayState:
        if state.battle_finished and not isinstance(event, BattleEnded):
            return self._with_status(state, ReplayReconstructionStatus.STATE_INCONSISTENCY)
        if isinstance(event, UnsupportedReplayEvent):
            return self._with_status(state, ReplayReconstructionStatus.UNSUPPORTED_PROTOCOL_EVENT)
        if isinstance(event, TurnStarted):
            if event.turn < state.turn:
                raise ReplayStateInvariantError(self.replay_id, event.metadata.line_number, "turn_regressed")
            return replace(state, turn=event.turn, pending_actions=())
        if isinstance(event, PokemonPreviewed):
            return self._add_preview(state, event)
        if isinstance(event, PokemonSwitched):
            return self._switch(state, event)
        if isinstance(event, MoveUsed):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, revealed_moves=pokemon.revealed_moves | {event.move_id}))
        if isinstance(event, HpChanged):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: _replace_hp(pokemon, event.hp_text))
        if isinstance(event, PokemonFainted):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, fainted=True, active=False, hp_current=0, hp_fraction=0.0))
        if isinstance(event, StatusApplied):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, status=event.status))
        if isinstance(event, StatusRemoved):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, status=None))
        if isinstance(event, BoostChanged):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, boosts=_boost(pokemon.boosts, event.stat, event.amount)))
        if isinstance(event, AbilityRevealed):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, revealed_ability=event.ability_id))
        if isinstance(event, ItemRevealed):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, revealed_item=event.item_id))
        if isinstance(event, ItemConsumed):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, revealed_item=None))
        if isinstance(event, TeraUsed):
            return self._update_pokemon(state, event.pokemon_ref, lambda pokemon: replace(pokemon, revealed_tera_type=event.tera_type))
        if isinstance(event, WeatherChanged):
            return replace(state, field=replace(state.field, weather=event.weather))
        if isinstance(event, TerrainChanged):
            return replace(state, field=replace(state.field, terrain=event.terrain))
        if isinstance(event, SideConditionStarted):
            return self._update_side(state, event.side, lambda side: replace(side, side_conditions=side.side_conditions | {event.condition}))
        if isinstance(event, SideConditionEnded):
            return self._update_side(state, event.side, lambda side: replace(side, side_conditions=side.side_conditions - {event.condition}))
        if isinstance(event, BattleEnded):
            return replace(state, battle_finished=True)
        return state

    def _add_preview(self, state: PublicReplayState, event: PokemonPreviewed) -> PublicReplayState:
        side = _side(state, event.side)
        species_id = _species_from_details(event.details)
        if any(pokemon.species_id == species_id for pokemon in side.pokemon):
            return self._with_status(state, ReplayReconstructionStatus.AMBIGUOUS_POKEMON_IDENTITY)
        pokemon = PublicPokemonState(
            replay_id=ReplayPokemonId(event.side, len(side.pokemon) + 1),
            replay_ref=f"{event.side}: {event.details}",
            species_id=species_id,
            hp_current=None,
            hp_max=None,
            hp_fraction=None,
            status=None,
            boosts=Boosts(),
            revealed_moves=frozenset(),
            revealed_item=None,
            revealed_ability=None,
            revealed_tera_type=None,
            fainted=False,
            active=False,
        )
        return self._update_side(state, event.side, lambda current: replace(current, pokemon=(*current.pokemon, pokemon)))

    def _switch(self, state: PublicReplayState, event: PokemonSwitched) -> PublicReplayState:
        side = _side(state, event.side)
        species_id = _species_from_details(event.details)
        matched = _match_pokemon(side, event.pokemon_ref, species_id)
        if matched is not None and matched.fainted:
            raise ReplayStateInvariantError(self.replay_id, event.metadata.line_number, "switch_to_fainted_pokemon")
        if matched is None:
            matched = PublicPokemonState(
                replay_id=ReplayPokemonId(event.side, len(side.pokemon) + 1),
                replay_ref=event.pokemon_ref,
                species_id=species_id,
                hp_current=None,
                hp_max=None,
                hp_fraction=None,
                status=None,
                boosts=Boosts(),
                revealed_moves=frozenset(),
                revealed_item=None,
                revealed_ability=None,
                revealed_tera_type=None,
                fainted=False,
                active=False,
            )
            side = replace(side, pokemon=(*side.pokemon, matched))
        updated = []
        for pokemon in side.pokemon:
            active = pokemon.replay_id == matched.replay_id
            replacement = replace(pokemon, active=active, replay_ref=event.pokemon_ref if active else pokemon.replay_ref)
            if active:
                replacement = _replace_hp(replacement, event.hp_text)
            updated.append(replacement)
        return self._replace_side(state, replace(side, pokemon=tuple(updated)))

    def _update_pokemon(self, state: PublicReplayState, ref: str, updater) -> PublicReplayState:
        side_id = ref.split(":", 1)[0][:2]
        side = _side(state, side_id)
        pokemon = _match_pokemon(side, ref, None)
        if pokemon is None:
            return self._with_status(state, ReplayReconstructionStatus.STATE_INCONSISTENCY)
        updated = tuple(updater(item) if item.replay_id == pokemon.replay_id else item for item in side.pokemon)
        return self._replace_side(state, replace(side, pokemon=updated))

    def _update_side(self, state: PublicReplayState, side_id: str, updater) -> PublicReplayState:
        return self._replace_side(state, updater(_side(state, side_id)))

    def _replace_side(self, state: PublicReplayState, new_side: PublicSideState) -> PublicReplayState:
        return replace(state, sides=tuple(new_side if side.side == new_side.side else side for side in state.sides))

    def _with_status(self, state: PublicReplayState, status: ReplayReconstructionStatus) -> PublicReplayState:
        if status in state.statuses:
            return state
        return replace(state, statuses=(*state.statuses, status))


def _side(state: PublicReplayState, side_id: str) -> PublicSideState:
    for side in state.sides:
        if side.side == side_id:
            return side
    raise ValueError(f"Unknown side: {side_id}")


def _match_pokemon(side: PublicSideState, ref: str, species_id: str | None) -> PublicPokemonState | None:
    for pokemon in side.pokemon:
        if pokemon.replay_ref == ref:
            return pokemon
    if species_id:
        matches = [pokemon for pokemon in side.pokemon if pokemon.species_id == species_id]
        if len(matches) == 1:
            return matches[0]
    active = next((pokemon for pokemon in side.pokemon if pokemon.active), None)
    if active is not None and ref.startswith(f"{side.side}a:"):
        return active
    return None


def _species_from_details(details: str) -> str:
    species = details.split(",", 1)[0].strip()
    if species.startswith("Mimikyu-"):
        species = "Mimikyu"
    return to_id(species)


def _replace_hp(pokemon: PublicPokemonState, hp_text: str) -> PublicPokemonState:
    hp_text = hp_text.split(" ", 1)[0]
    if hp_text == "0" or hp_text.startswith("0 "):
        return replace(pokemon, hp_current=0, hp_fraction=0.0, fainted=True)
    if "/" not in hp_text:
        return pokemon
    current_text, max_text = hp_text.split("/", 1)
    try:
        current = int(current_text)
        maximum = int(max_text)
    except ValueError:
        return pokemon
    if current < 0:
        raise ValueError("negative_hp")
    if maximum == 100:
        return replace(pokemon, hp_current=None, hp_max=None, hp_fraction=current / 100, fainted=current <= 0)
    return replace(pokemon, hp_current=current, hp_max=maximum, hp_fraction=current / maximum if maximum else None, fainted=current <= 0)


def _boost(boosts: Boosts, stat: str, amount: int) -> Boosts:
    if not hasattr(boosts, stat):
        return boosts
    value = max(-6, min(6, getattr(boosts, stat) + amount))
    return replace(boosts, **{stat: value})
