from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pokebrain.search.policy import PolicyCalibration, PolicyProfile, PolicyWeights


def load_policy_profile(path: Path) -> PolicyProfile:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return PolicyProfile(
        format_id=str(data["format_id"]),
        rating_bucket=data.get("rating_bucket"),
        weights=PolicyWeights(**data.get("weights", {})),
        calibration=PolicyCalibration(**data.get("calibration", {})),
    )


def save_policy_profile(profile: PolicyProfile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(profile_to_dict(profile), file, indent=2, sort_keys=True)
        file.write("\n")


def profile_to_dict(profile: PolicyProfile) -> dict[str, Any]:
    return asdict(profile)
