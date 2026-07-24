from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SampledTeam:
    team_id: str
    path: Path


class TeamSampler:
    def __init__(self, team_pool_path: Path | str) -> None:
        self.team_pool_path = Path(team_pool_path)
        self.teams = tuple(sorted(self.team_pool_path.glob("*.txt")))
        if not self.teams:
            raise ValueError(f"No .txt teams found in {self.team_pool_path}")

    def sample_pair(self, seed: tuple[int, int, int, int]) -> tuple[SampledTeam, SampledTeam]:
        random_source = random.Random(sum(seed))
        if len(self.teams) == 1:
            first = second = self.teams[0]
        else:
            first, second = random_source.sample(self.teams, 2)
        return self._sampled(first), self._sampled(second)

    def _sampled(self, path: Path) -> SampledTeam:
        return SampledTeam(team_id=path.stem, path=path)
