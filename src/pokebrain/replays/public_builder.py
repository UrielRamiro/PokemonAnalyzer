from __future__ import annotations

from dataclasses import replace

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.replays.public_events import MoveUsed, PokemonSwitched
from pokebrain.replays.public_models import (
    ObservedAction,
    PartialPolicyExample,
    PublicReplayState,
    ReconstructedDecision,
    ReplayReconstructionStatus,
    ReplaySnapshot,
)


class PolicyExampleBuilder:
    def build(
        self,
        replay_id: str,
        snapshots: tuple[ReplaySnapshot, ...],
        events,
    ) -> tuple[ReconstructedDecision, ...]:
        turn_start = {snapshot.turn: snapshot for snapshot in snapshots if snapshot.phase == "turn_start"}
        decisions: list[ReconstructedDecision] = []
        seen: set[tuple[int, str]] = set()
        for event in events:
            if not isinstance(event, (MoveUsed, PokemonSwitched)):
                continue
            turn = event.metadata.turn_number
            if turn is None or turn not in turn_start:
                continue
            side = event.side
            key = (turn, side)
            if key in seen:
                continue
            seen.add(key)
            action = _observed_action(event, turn)
            decisions.append(
                ReconstructedDecision(
                    state_before_turn=turn_start[turn].state,
                    actual_action=action,
                    legal_actions=None,
                    reconstruction_confidence="partial",
                    missing_information=("legal_actions", "full_team_information"),
                )
            )
        return tuple(decisions)

    def build_partial_examples(self, decisions: tuple[ReconstructedDecision, ...]) -> tuple[PartialPolicyExample, ...]:
        return tuple(
            PartialPolicyExample(
                observed_state=decision.state_before_turn,
                actual_action=decision.actual_action,
                candidate_actions=decision.legal_actions,
                missing_information=decision.missing_information,
            )
            for decision in decisions
        )


def _observed_action(event: MoveUsed | PokemonSwitched, turn: int) -> ObservedAction:
    if isinstance(event, MoveUsed):
        return ObservedAction(
            side=event.side,
            action=BattleAction(ActionType.MOVE, move_id=event.move_id),
            pokemon_ref=event.pokemon_ref,
            turn=turn,
        )
    return ObservedAction(
        side=event.side,
        action=BattleAction(ActionType.SWITCH, switch_target_id=_species_from_details(event.details)),
        pokemon_ref=event.pokemon_ref,
        turn=turn,
    )


def _species_from_details(details: str) -> str:
    from pokebrain.utils import to_id

    return to_id(details.split(",", 1)[0].strip())
