from __future__ import annotations

from dataclasses import replace

from pokebrain.battle.models import ActivePokemonState, BattleSideState, BattleState
from pokebrain.battle_protocol.events import (
    BattleEvent,
    DamageEvent,
    FaintEvent,
    HealEvent,
    SideEndEvent,
    SideStartEvent,
    TurnEvent,
    WeatherEvent,
)
from pokebrain.battle_protocol.identifiers import player_id_from_identifier, species_id_from_identifier
from pokebrain.local_agent import current_hp_from_condition


class BattleStateReducer:
    def apply(self, state: BattleState, event: BattleEvent) -> BattleState:
        if isinstance(event, TurnEvent):
            return replace(state, turn=event.turn)
        if isinstance(event, WeatherEvent):
            return replace(state, weather=event.weather)
        if isinstance(event, DamageEvent | HealEvent):
            return self._apply_hp_change(state, event.pokemon_identifier, event.condition)
        if isinstance(event, FaintEvent):
            return self._apply_faint(state, event.pokemon_identifier)
        if isinstance(event, SideStartEvent | SideEndEvent):
            return self._apply_side_condition(state, event)
        return state

    def _apply_hp_change(self, state: BattleState, identifier: str, condition: str) -> BattleState:
        player_id = player_id_from_identifier(identifier)
        hp = current_hp_from_condition(condition)
        if player_id == "p1":
            return replace(state, player=_replace_active_hp(state.player, hp))
        if player_id == "p2":
            return replace(state, opponent=_replace_active_hp(state.opponent, hp))
        return state

    def _apply_faint(self, state: BattleState, identifier: str) -> BattleState:
        player_id = player_id_from_identifier(identifier)
        species_id = species_id_from_identifier(identifier)
        if player_id == "p1":
            return replace(
                state,
                player=replace(
                    _replace_active_hp(state.player, 0),
                    fainted_ids=tuple(sorted(set(state.player.fainted_ids + (species_id,)))),
                ),
            )
        if player_id == "p2":
            return replace(
                state,
                opponent=replace(
                    _replace_active_hp(state.opponent, 0),
                    fainted_ids=tuple(sorted(set(state.opponent.fainted_ids + (species_id,)))),
                ),
            )
        return state

    def _apply_side_condition(self, state: BattleState, event: SideStartEvent | SideEndEvent) -> BattleState:
        player_id = player_id_from_identifier(event.side_identifier)
        enabled = isinstance(event, SideStartEvent)
        effect = event.effect.lower()
        if "stealth rock" not in effect:
            return state
        if player_id == "p1":
            return replace(state, player=replace(state.player, stealth_rock=enabled))
        if player_id == "p2":
            return replace(state, opponent=replace(state.opponent, stealth_rock=enabled))
        return state


def _replace_active_hp(side: BattleSideState, hp: int) -> BattleSideState:
    return replace(side, active=replace(side.active, current_hp=hp))
