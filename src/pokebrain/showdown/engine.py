from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol


ROOT_DIR = Path(__file__).resolve().parents[3]
ResolveKind = Literal["species", "move", "ability", "item"]


@dataclass(frozen=True, slots=True)
class TeamValidationResult:
    valid: bool
    format_id: str
    problems: tuple[str, ...]

    @property
    def errors(self) -> tuple[str, ...]:
        return self.problems


class CompetitiveRulesEngine(Protocol):
    def validate_team(
        self,
        format_id: str,
        team_text: str,
    ) -> TeamValidationResult:
        ...


class ShowdownEngine:
    def __init__(self, root_dir: Path | str = ROOT_DIR) -> None:
        self.root_dir = Path(root_dir)

    def resolve(self, mod: str, kind: ResolveKind, name_or_id: str) -> dict[str, Any] | None:
        payload = self._run_bridge(
            [
                "resolve",
                "--mod",
                mod,
                "--kind",
                kind,
                "--id",
                name_or_id,
            ]
        )
        if not payload["found"]:
            return None
        return payload["data"]

    def validate_team(self, format_id: str, team_text: str) -> TeamValidationResult:
        payload = self._run_bridge(
            [
                "validate-team",
                "--format",
                format_id,
            ],
            input_text=team_text,
        )

        return TeamValidationResult(
            valid=payload["valid"],
            format_id=payload["format"],
            problems=tuple(payload["problems"]),
        )

    def list_formats(self) -> list[dict[str, Any]]:
        payload = self._run_bridge(["list-formats"])
        return payload["formats"]

    def _run_bridge(
        self,
        args: list[str],
        input_text: str | None = None,
    ) -> dict[str, Any]:
        command = ["node", "scripts/showdown_bridge.js", *args]
        completed = subprocess.run(
            command,
            cwd=self.root_dir,
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
        )

        output = completed.stdout.strip()
        if not output:
            raise RuntimeError(completed.stderr.strip() or "Showdown bridge returned no output.")

        payload = json.loads(output)
        if completed.returncode != 0 or not payload.get("ok"):
            raise RuntimeError(payload.get("error", "Showdown bridge failed."))

        return payload
