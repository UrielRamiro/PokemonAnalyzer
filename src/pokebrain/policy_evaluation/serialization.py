from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.policy_evaluation.models import ErrorInspectionCase, PolicyComparison, PolicyEvaluationReport


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, sort_keys=True)
        file.write("\n")


def report_to_json(report: PolicyEvaluationReport) -> dict[str, Any]:
    return {
        "summary": asdict(report.summary),
        "confidence_intervals": [asdict(item) for item in report.confidence_intervals],
        "calibration_curve": [asdict(item) for item in report.calibration_curve],
        "error_buckets": [(name, asdict(summary)) for name, summary in report.error_buckets],
        "matchup_buckets": [(name, asdict(summary)) for name, summary in report.matchup_buckets],
        "inspection_cases": [_case_to_json(case) for case in report.inspection_cases],
    }


def comparison_to_json(comparison: PolicyComparison) -> dict[str, Any]:
    return asdict(comparison)


def _case_to_json(case: ErrorInspectionCase) -> dict[str, Any]:
    payload = asdict(case)
    payload["actual_action"] = _action_to_json(case.actual_action)
    payload["top_prediction"] = _action_to_json(case.top_prediction) if case.top_prediction else None
    return payload


def _action_to_json(action: BattleAction) -> dict[str, object]:
    if action.action_type is ActionType.MOVE:
        return {"type": "move", "move_id": action.move_id}
    return {"type": "switch", "switch_target_id": action.switch_target_id}
