from __future__ import annotations

from pokebrain.battle.models import ActionType, BattleAction, BattleSideState, BattleState


class LegalActionGenerator:
    def generate(self, state: BattleState) -> tuple[BattleAction, ...]:
        return self.generate_for_side(state.player)

    def generate_for_side(self, side: BattleSideState) -> tuple[BattleAction, ...]:
        actions: list[BattleAction] = []
        active = side.active

        for move_id in active.set_data.moves:
            actions.append(BattleAction(action_type=ActionType.MOVE, move_id=move_id))

        if not active.trapped:
            for member in side.team:
                if member.species_id == active.set_data.species_id:
                    continue
                if member.species_id in side.fainted_ids:
                    continue
                actions.append(
                    BattleAction(
                        action_type=ActionType.SWITCH,
                        switch_target_id=member.species_id,
                    )
                )

        return tuple(actions)

