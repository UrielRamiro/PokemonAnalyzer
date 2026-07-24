from __future__ import annotations

from pokebrain.replays.public_builder import PolicyExampleBuilder
from pokebrain.replays.public_events import BattleEnded, ReplayEvent, TurnStarted, UnsupportedReplayEvent
from pokebrain.replays.public_models import ParsedPublicReplay, ReplayReconstructionStatus, ReplaySnapshot, ReplayStateInvariantError
from pokebrain.replays.public_protocol import ReplayProtocolParser
from pokebrain.replays.public_reducer import PublicReplayStateReducer


class PublicReplayParser:
    def __init__(
        self,
        protocol_parser: ReplayProtocolParser | None = None,
        reducer: PublicReplayStateReducer | None = None,
        builder: PolicyExampleBuilder | None = None,
    ) -> None:
        self.protocol_parser = protocol_parser or ReplayProtocolParser()
        self.reducer = reducer
        self.builder = builder or PolicyExampleBuilder()

    def parse(self, *, replay_id: str, format_id: str, raw_log: str) -> ParsedPublicReplay:
        if not _supported_format(format_id):
            return ParsedPublicReplay(
                replay_id=replay_id,
                format_id=format_id,
                events=(),
                snapshots=(),
                decisions=(),
                partial_examples=(),
                statuses=(ReplayReconstructionStatus.UNSUPPORTED_FORMAT,),
            )
        events = self.protocol_parser.parse(raw_log)
        reducer = self.reducer or PublicReplayStateReducer(replay_id)
        state = reducer.initial_state()
        snapshots: list[ReplaySnapshot] = []
        statuses: set[ReplayReconstructionStatus] = set()
        for event in events:
            if isinstance(event, TurnStarted):
                state = reducer.apply(state, event)
                snapshots.append(
                    ReplaySnapshot(
                        replay_id=replay_id,
                        turn=state.turn,
                        phase="turn_start",
                        state=state,
                        source_line_number=event.metadata.line_number,
                    )
                )
                continue
            try:
                state = reducer.apply(state, event)
            except (ReplayStateInvariantError, ValueError):
                statuses.add(ReplayReconstructionStatus.STATE_INCONSISTENCY)
                break
            statuses.update(state.statuses)
            if isinstance(event, BattleEnded):
                snapshots.append(
                    ReplaySnapshot(
                        replay_id=replay_id,
                        turn=state.turn,
                        phase="battle_end",
                        state=state,
                        source_line_number=event.metadata.line_number,
                    )
                )
        if any(isinstance(event, UnsupportedReplayEvent) for event in events):
            statuses.add(ReplayReconstructionStatus.UNSUPPORTED_PROTOCOL_EVENT)
        if events and not any(snapshot.phase == "battle_end" for snapshot in snapshots):
            snapshots.append(
                ReplaySnapshot(
                    replay_id=replay_id,
                    turn=state.turn,
                    phase="turn_end",
                    state=state,
                    source_line_number=events[-1].metadata.line_number,
                )
            )
        decisions = self.builder.build(replay_id, tuple(snapshots), events)
        partial_examples = self.builder.build_partial_examples(decisions)
        if decisions and all(decision.legal_actions is None for decision in decisions):
            statuses.add(ReplayReconstructionStatus.PARTIAL_MISSING_LEGAL_ACTIONS)
        if partial_examples:
            statuses.add(ReplayReconstructionStatus.PARTIAL_MISSING_TEAM)
        if not statuses:
            statuses.add(ReplayReconstructionStatus.COMPLETE)
        return ParsedPublicReplay(
            replay_id=replay_id,
            format_id=format_id,
            events=events,
            snapshots=tuple(snapshots),
            decisions=decisions,
            partial_examples=partial_examples,
            statuses=tuple(sorted(statuses, key=lambda item: item.value)),
        )


def _supported_format(format_id: str) -> bool:
    return format_id.startswith("gen9") and "doubles" not in format_id and "vgc" not in format_id
