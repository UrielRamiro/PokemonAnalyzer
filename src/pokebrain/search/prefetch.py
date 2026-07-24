from __future__ import annotations

from pokebrain.battle.models import ActionType, BattleAction, BattleState
from pokebrain.damage import DamageRequest, FieldState
from pokebrain.damage.engine import DamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.team.models import PokemonSet


class SearchDamagePrefetcher:
    def __init__(self, data_manager: DataManager | None = None) -> None:
        self.data_manager = data_manager or DataManager()

    def collect_requests(
        self,
        state: BattleState,
        player_actions: tuple[BattleAction, ...],
        opponent_actions: tuple[BattleAction, ...],
    ) -> tuple[DamageRequest, ...]:
        requests: list[DamageRequest] = []
        player_switches = tuple(action.switch_target_id for action in player_actions if action.action_type is ActionType.SWITCH and action.switch_target_id)
        opponent_switches = tuple(action.switch_target_id for action in opponent_actions if action.action_type is ActionType.SWITCH and action.switch_target_id)

        for action in player_actions:
            if self._is_damaging_move(action):
                requests.append(self._request(state, "player", action.move_id))
                for target_id in opponent_switches:
                    target = self._team_member(state, "opponent", target_id)
                    if target is not None:
                        requests.append(self._request(state, "player", action.move_id, defender=target))

        for action in opponent_actions:
            if self._is_damaging_move(action):
                requests.append(self._request(state, "opponent", action.move_id))
                for target_id in player_switches:
                    target = self._team_member(state, "player", target_id)
                    if target is not None:
                        requests.append(self._request(state, "opponent", action.move_id, defender=target))

        return tuple(requests)

    def prefetch(
        self,
        damage_engine: DamageEngine,
        state: BattleState,
        player_actions: tuple[BattleAction, ...],
        opponent_actions: tuple[BattleAction, ...],
    ) -> None:
        requests = self.collect_requests(state, player_actions, opponent_actions)
        if not requests:
            return
        if hasattr(damage_engine, "calculate_many"):
            damage_engine.calculate_many(requests)
            return
        for request in requests:
            damage_engine.calculate(request)

    def _request(
        self,
        state: BattleState,
        side: str,
        move_id: str,
        defender: PokemonSet | None = None,
    ) -> DamageRequest:
        attacker = state.player.active.set_data if side == "player" else state.opponent.active.set_data
        if defender is None:
            defender = state.opponent.active.set_data if side == "player" else state.player.active.set_data
        return DamageRequest(
            generation=state.generation,
            format_id=state.format_id,
            attacker=attacker,
            defender=defender,
            move_id=move_id,
            field=FieldState(weather=state.weather, terrain=state.terrain),
        )

    def _team_member(self, state: BattleState, side: str, species_id: str) -> PokemonSet | None:
        battle_side = state.player if side == "player" else state.opponent
        return next((member for member in battle_side.team if member.species_id == species_id), None)

    def _is_damaging_move(self, action: BattleAction) -> bool:
        if action.action_type is not ActionType.MOVE or not action.move_id:
            return False
        move = self.data_manager.moves.get_by_id(action.move_id)
        return move is not None and move.category != "Status"
