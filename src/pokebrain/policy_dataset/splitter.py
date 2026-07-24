from __future__ import annotations

from pokebrain.policy_dataset.models import DatasetSplit, PolicyDatasetRecord


class PolicyDatasetSplitter:
    def split_by_battle_group(
        self,
        records: tuple[PolicyDatasetRecord, ...],
        *,
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
    ) -> DatasetSplit:
        groups = _battle_groups(records)
        ordered_keys = tuple(sorted(groups, key=lambda key: (_group_upload_time(groups[key]), key)))
        total = len(ordered_keys)
        train_end = int(total * train_ratio)
        validation_end = train_end + int(total * validation_ratio)
        train_keys = set(ordered_keys[:train_end])
        validation_keys = set(ordered_keys[train_end:validation_end])
        train = []
        validation = []
        test = []
        for key in ordered_keys:
            destination = train if key in train_keys else validation if key in validation_keys else test
            destination.extend(sorted(groups[key], key=lambda record: record.metadata.turn_number))
        return DatasetSplit(tuple(train), tuple(validation), tuple(test))


def _battle_groups(records: tuple[PolicyDatasetRecord, ...]) -> dict[str, list[PolicyDatasetRecord]]:
    groups: dict[str, list[PolicyDatasetRecord]] = {}
    for record in records:
        groups.setdefault(record.metadata.replay_id, []).append(record)
    return groups


def _group_upload_time(records: list[PolicyDatasetRecord]) -> int:
    return min(record.metadata.upload_time for record in records)
