from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.policy_dataset.models import (
    BaselineReport,
    FingerprintReport,
    PolicyDatasetAuditReport,
    PolicyDatasetDiversityReport,
    PolicyDatasetManifest,
    PolicyDatasetRecord,
    PolicyDatasetReport,
)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def record_to_json(record: PolicyDatasetRecord) -> dict[str, Any]:
    return {
        "metadata": asdict(record.metadata),
        "features": {
            "schema_version": record.features.schema_version if record.features else None,
            "values": list(record.features.values) if record.features else [],
        },
        "actual_action": action_to_json(record.example.actual_action),
        "legal_actions": [action_to_json(action) for action in record.example.legal_actions],
    }


def write_records_jsonl(path: Path, records: tuple[PolicyDatasetRecord, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record_to_json(record), sort_keys=True))
            file.write("\n")


def action_to_json(action: BattleAction) -> dict[str, object]:
    if action.action_type is ActionType.MOVE:
        payload = {"type": "move", "move_id": action.move_id}
    else:
        payload = {"type": "switch", "switch_target_id": action.switch_target_id}
    if action.action_id:
        payload["action_id"] = action.action_id
    return payload


def manifest_to_json(manifest: PolicyDatasetManifest) -> dict[str, Any]:
    return asdict(manifest)


def quality_report_to_json(report: PolicyDatasetReport) -> dict[str, Any]:
    return asdict(report)


def baseline_report_to_json(report: BaselineReport) -> dict[str, Any]:
    return asdict(report)


def audit_report_to_json(report: PolicyDatasetAuditReport) -> dict[str, Any]:
    return asdict(report)


def diversity_report_to_json(report: PolicyDatasetDiversityReport) -> dict[str, Any]:
    return asdict(report)


def fingerprint_report_to_json(report: FingerprintReport) -> dict[str, Any]:
    return asdict(report)
