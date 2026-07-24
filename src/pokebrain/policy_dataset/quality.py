from __future__ import annotations

from collections import Counter

from pokebrain.battle.models import ActionType
from pokebrain.policy_dataset.models import CoverageReport, PolicyDatasetRecord, PolicyDatasetReport
from pokebrain.replays.catalog import ReplayCatalog


class DataQualityReporter:
    def report(self, records: tuple[PolicyDatasetRecord, ...]) -> PolicyDatasetReport:
        formats = Counter(record.metadata.format_id for record in records)
        turns = Counter(_turn_bucket(record.metadata.turn_number) for record in records)
        actions = Counter(_action_type(record) for record in records)
        return PolicyDatasetReport(
            total_decisions=len(records),
            by_format=tuple(sorted(formats.items())),
            by_turn_bucket=tuple(sorted(turns.items())),
            by_action_type=tuple(sorted(actions.items())),
            feature_coverage=_feature_coverage(records),
        )


class CoverageReporter:
    def from_catalog(self, catalog: ReplayCatalog, format_id: str) -> CoverageReport:
        rows = catalog.list_all(format_id=format_id)
        status = Counter(row.parse_status for row in rows)
        reasons = Counter(row.failure_reason or "none" for row in rows)
        return CoverageReport(
            catalog_total=len(rows),
            complete_examples=status.get("parsed", 0),
            partial_examples=status.get("partial", 0),
            status_counts=tuple(sorted(status.items())),
            reason_counts=tuple(sorted(reasons.items())),
        )


def _turn_bucket(turn: int) -> str:
    if turn <= 5:
        return "turns_1_5"
    if turn <= 10:
        return "turns_6_10"
    if turn <= 20:
        return "turns_11_20"
    return "turns_20_plus"


def _action_type(record: PolicyDatasetRecord) -> str:
    action = record.example.actual_action
    if action.action_type is ActionType.SWITCH:
        return "switch"
    move_id = action.move_id or ""
    if move_id in {"recover", "roost", "moonlight", "synthesis", "slackoff", "softboiled", "painsplit"}:
        return "recover"
    if move_id in {"uturn", "voltswitch", "flipturn", "partingshot", "chillyreception"}:
        return "pivot"
    if move_id in {"swordsdance", "nastyplot", "dragondance", "calmmind", "agility"}:
        return "setup"
    return "attack"


def _feature_coverage(records: tuple[PolicyDatasetRecord, ...]) -> tuple[tuple[str, float], ...]:
    if not records:
        return ()
    item_known = sum(1 for record in records if record.example.observed_state.opponent.active.set_data.item_id)
    ability_known = sum(1 for record in records if record.example.observed_state.opponent.active.set_data.ability_id)
    move_4_known = sum(1 for record in records if len(record.example.observed_state.opponent.active.set_data.moves) >= 4)
    hp_known = sum(1 for record in records if record.example.observed_state.opponent.active.current_hp >= 0)
    total = len(records)
    return (
        ("hp_known", hp_known / total),
        ("item_known", item_known / total),
        ("ability_known", ability_known / total),
        ("move_4_known", move_4_known / total),
    )
