from __future__ import annotations

from pokebrain.battle.models import BattleState


def swap_perspective(state: BattleState) -> BattleState:
    return BattleState(
        generation=state.generation,
        format_id=state.format_id,
        turn=state.turn,
        player=state.opponent,
        opponent=state.player,
        weather=state.weather,
        terrain=state.terrain,
        trick_room_turns=state.trick_room_turns,
    )
