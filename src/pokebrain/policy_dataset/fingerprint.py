from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from pokebrain.battle.models import ActionType, BattleAction, BattleState
from pokebrain.policy_dataset.models import FingerprintReport, PolicyDatasetRecord, PolicyExampleFingerprint


def fingerprint_record(record: PolicyDatasetRecord) -> PolicyExampleFingerprint:
    state = record.example.observed_state
    return PolicyExampleFingerprint(
        format_id=record.metadata.format_id,
        observable_state_hash=_hash(_observable_state_payload(state)),
        actor_private_state_hash=_hash(_actor_private_state_payload(state)),
        legal_actions_hash=_hash([_action_id(action) for action in record.example.legal_actions]),
        actual_action_id=_action_id(record.example.actual_action),
    )


def fingerprint_report(records: tuple[PolicyDatasetRecord, ...]) -> FingerprintReport:
    fingerprints = tuple(fingerprint_record(record) for record in records)
    unique = set(fingerprints)
    state_to_actions: dict[tuple[str, str, str], set[str]] = {}
    for fingerprint in fingerprints:
        key = (
            fingerprint.format_id,
            fingerprint.observable_state_hash,
            fingerprint.legal_actions_hash,
        )
        state_to_actions.setdefault(key, set()).add(fingerprint.actual_action_id)
    return FingerprintReport(
        total_examples=len(records),
        unique_fingerprints=len(unique),
        exact_duplicates=len(records) - len(unique),
        same_state_different_actions=sum(1 for actions in state_to_actions.values() if len(actions) > 1),
    )


def _observable_state_payload(state: BattleState) -> dict[str, object]:
    return {
        "generation": state.generation,
        "format_id": state.format_id,
        "turn": state.turn,
        "player": asdict(state.player),
        "opponent_active": asdict(state.opponent.active),
        "opponent_revealed_team": tuple(asdict(member) for member in state.opponent.team),
        "weather": state.weather,
        "terrain": state.terrain,
        "trick_room_turns": state.trick_room_turns,
    }


def _actor_private_state_payload(state: BattleState) -> dict[str, object]:
    return {
        "player_team": tuple(asdict(member) for member in state.player.team),
        "player_active": asdict(state.player.active),
    }


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _action_id(action: BattleAction) -> str:
    if action.action_type is ActionType.MOVE:
        return f"move:{action.move_id or ''}"
    return f"switch:{action.switch_target_id or ''}"
