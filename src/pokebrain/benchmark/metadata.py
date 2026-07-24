from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict

from pokebrain.benchmark.models import AgentMetadata, BenchmarkConfig


def build_agent_metadata(agent_name: str, config: BenchmarkConfig) -> AgentMetadata:
    return AgentMetadata(
        version=agent_name,
        git_commit=current_git_commit(),
        configuration_hash=configuration_hash(agent_name, config),
    )


def configuration_hash(agent_name: str, config: BenchmarkConfig) -> str:
    payload = {
        "agent": agent_name,
        "format_id": config.format_id,
        "maximum_turns": config.maximum_turns,
        "timeout_seconds": config.timeout_seconds,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def current_git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None
