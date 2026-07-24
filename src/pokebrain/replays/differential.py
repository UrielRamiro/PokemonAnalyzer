from __future__ import annotations

from dataclasses import dataclass

from pokebrain.battle.models import BattleState
from pokebrain.replays.public_models import PublicReplayState


@dataclass(frozen=True, slots=True)
class ReplayDiff:
    turn: int
    field: str
    expected: str
    actual: str


@dataclass(frozen=True, slots=True)
class ReplayDiffReport:
    compared: int
    diffs: tuple[ReplayDiff, ...]

    @property
    def passed(self) -> bool:
        return not self.diffs


class ReplayDifferentialValidator:
    def compare(
        self,
        authoritative_snapshots: tuple[BattleState, ...],
        reconstructed_snapshots: tuple[PublicReplayState, ...],
    ) -> ReplayDiffReport:
        diffs: list[ReplayDiff] = []
        for expected, actual in zip(authoritative_snapshots, reconstructed_snapshots):
            if expected.turn != actual.turn:
                diffs.append(ReplayDiff(actual.turn, "turn", str(expected.turn), str(actual.turn)))
            for side_name, expected_side in (("p1", expected.player), ("p2", expected.opponent)):
                public_side = next((side for side in actual.sides if side.side == side_name), None)
                public_active = next((pokemon for pokemon in public_side.pokemon if pokemon.active), None) if public_side else None
                expected_species = expected_side.active.set_data.species_id
                actual_species = public_active.species_id if public_active else None
                if actual_species is not None and expected_species != actual_species:
                    diffs.append(ReplayDiff(actual.turn, f"{side_name}.active_species", expected_species, actual_species))
        return ReplayDiffReport(compared=min(len(authoritative_snapshots), len(reconstructed_snapshots)), diffs=tuple(diffs))
