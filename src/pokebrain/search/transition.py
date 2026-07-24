from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from pokebrain.analysis.stats import StatCalculator
from pokebrain.battle.models import ActionType, ActivePokemonState, BattleAction, BattleSideState, BattleState
from pokebrain.damage import CachedDamageEngine, DamageRequest, FieldState, ShowdownDamageEngine
from pokebrain.damage.engine import DamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.search.models import StateTransition
from pokebrain.search.prefetch import SearchDamagePrefetcher
from pokebrain.team.models import PokemonSet


class BattleTransitionModel(Protocol):
    def resolve_turn(
        self,
        state: BattleState,
        player_action: BattleAction,
        opponent_action: BattleAction,
    ) -> tuple[StateTransition, ...]:
        ...


class DeterministicBattleTransitionModel:
    limitations = (
        "Uses average damage rolls.",
        "Assumes damaging moves hit.",
        "Ignores critical hits and secondary effects.",
        "Uses simple speed ordering and simplified switch timing.",
        "Forced switches after KO are not expanded.",
    )

    def __init__(
        self,
        damage_engine: DamageEngine | None = None,
        data_manager: DataManager | None = None,
        enable_damage_prefetch: bool = False,
        reset_damage_scope_each_search: bool = True,
    ) -> None:
        self.damage_engine = damage_engine or CachedDamageEngine(ShowdownDamageEngine())
        self.data_manager = data_manager or DataManager()
        self.stats = StatCalculator()
        self.enable_damage_prefetch = enable_damage_prefetch
        self.reset_damage_scope_each_search = reset_damage_scope_each_search
        self.prefetcher = SearchDamagePrefetcher(self.data_manager)

    def begin_search_scope(self) -> None:
        if self.reset_damage_scope_each_search and hasattr(self.damage_engine, "begin_search_scope"):
            self.damage_engine.begin_search_scope()

    def prefetch_damage(
        self,
        state: BattleState,
        player_actions: tuple[BattleAction, ...],
        opponent_actions: tuple[BattleAction, ...],
    ) -> None:
        if not self.enable_damage_prefetch:
            return
        self.prefetcher.prefetch(self.damage_engine, state, player_actions, opponent_actions)

    def resolve_turn(
        self,
        state: BattleState,
        player_action: BattleAction,
        opponent_action: BattleAction,
    ) -> tuple[StateTransition, ...]:
        next_state = state
        if player_action.action_type is ActionType.SWITCH:
            next_state = self._switch(next_state, "player", player_action.switch_target_id)
        if opponent_action.action_type is ActionType.SWITCH:
            next_state = self._switch(next_state, "opponent", opponent_action.switch_target_id)

        move_order = self._move_order(next_state, player_action, opponent_action)
        for side, action in move_order:
            if self._active(next_state, side).current_hp <= 0:
                continue
            target_side = "opponent" if side == "player" else "player"
            if self._active(next_state, target_side).current_hp <= 0:
                continue
            next_state = self._apply_move(next_state, side, action)

        return (StateTransition(probability=1.0, next_state=next_state),)

    def _move_order(self, state: BattleState, player_action: BattleAction, opponent_action: BattleAction):
        actions = []
        if player_action.action_type is ActionType.MOVE:
            actions.append(("player", player_action))
        if opponent_action.action_type is ActionType.MOVE:
            actions.append(("opponent", opponent_action))
        return tuple(sorted(actions, key=lambda item: self._priority_speed_key(state, item[0], item[1]), reverse=True))

    def _priority_speed_key(self, state: BattleState, side: str, action: BattleAction) -> tuple[int, int]:
        move = self.data_manager.moves.get_by_id(action.move_id or "")
        priority = move.priority if move is not None else 0
        return priority, self._speed(self._active(state, side).set_data, state.format_id)

    def _apply_move(self, state: BattleState, side: str, action: BattleAction) -> BattleState:
        if action.move_id is None:
            return state
        move = self.data_manager.moves.get_by_id(action.move_id)
        if move is None or move.category == "Status":
            return self._apply_status_move(state, side, action.move_id)

        attacker = self._active(state, side).set_data
        defender_side = "opponent" if side == "player" else "player"
        defender = self._active(state, defender_side)
        damage = self.damage_engine.calculate(
            DamageRequest(
                generation=state.generation,
                attacker=attacker,
                defender=defender.set_data,
                move_id=action.move_id,
                field=FieldState(weather=state.weather, terrain=state.terrain),
                format_id=state.format_id,
            )
        )
        average_damage = (damage.minimum_damage + damage.maximum_damage) / 2
        average_percent = (damage.minimum_percent + damage.maximum_percent) / 2
        hp_damage = average_percent if defender.current_hp <= 100 else average_damage
        next_state = self._replace_active_hp(state, defender_side, max(0, int(defender.current_hp - hp_damage)))
        if action.move_id in {"rapidspin", "mortalspin", "tidyup"}:
            return self._clear_own_hazards(next_state, side)
        if action.move_id == "defog":
            return replace(
                next_state,
                player=replace(next_state.player, stealth_rock=False, spikes_layers=0),
                opponent=replace(next_state.opponent, stealth_rock=False, spikes_layers=0),
            )
        return next_state

    def _apply_status_move(self, state: BattleState, side: str, move_id: str) -> BattleState:
        if move_id == "stealthrock":
            if side == "player":
                return replace(state, opponent=replace(state.opponent, stealth_rock=True))
            return replace(state, player=replace(state.player, stealth_rock=True))
        if move_id == "spikes":
            if side == "player":
                return replace(state, opponent=replace(state.opponent, spikes_layers=min(3, state.opponent.spikes_layers + 1)))
            return replace(state, player=replace(state.player, spikes_layers=min(3, state.player.spikes_layers + 1)))
        if move_id in {"rapidspin", "defog", "mortalspin", "tidyup"}:
            return self._clear_own_hazards(state, side)
        return state

    def _clear_own_hazards(self, state: BattleState, side: str) -> BattleState:
        if side == "player":
            return replace(state, player=replace(state.player, stealth_rock=False, spikes_layers=0))
        return replace(state, opponent=replace(state.opponent, stealth_rock=False, spikes_layers=0))

    def _switch(self, state: BattleState, side: str, target_id: str | None) -> BattleState:
        if target_id is None:
            return state
        battle_side = state.player if side == "player" else state.opponent
        target = next((member for member in battle_side.team if member.species_id == target_id), None)
        if target is None:
            return state
        current_hp = self._max_hp(target, state.format_id)
        updated = replace(battle_side, active=ActivePokemonState(set_data=target, current_hp=current_hp))
        return replace(state, player=updated) if side == "player" else replace(state, opponent=updated)

    def _replace_active_hp(self, state: BattleState, side: str, hp: int) -> BattleState:
        battle_side = state.player if side == "player" else state.opponent
        fainted = battle_side.fainted_ids
        if hp <= 0 and battle_side.active.set_data.species_id not in fainted:
            fainted = tuple(sorted((*fainted, battle_side.active.set_data.species_id)))
        updated = replace(battle_side, active=replace(battle_side.active, current_hp=hp), fainted_ids=fainted)
        return replace(state, player=updated) if side == "player" else replace(state, opponent=updated)

    def _active(self, state: BattleState, side: str):
        return state.player.active if side == "player" else state.opponent.active

    def _speed(self, pokemon_set: PokemonSet, format_id: str | None = None) -> int:
        species = self.data_manager.species.get_by_id(pokemon_set.species_id)
        if species is None:
            return 0
        return self.stats.calculate(pokemon_set, species, format_id).speed

    def _max_hp(self, pokemon_set: PokemonSet, format_id: str | None = None) -> int:
        species = self.data_manager.species.get_by_id(pokemon_set.species_id)
        if species is None:
            return 100
        return self.stats.calculate(pokemon_set, species, format_id).hp
