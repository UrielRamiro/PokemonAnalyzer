from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from pokebrain.policy_dataset.baselines import BaselineEvaluator
from pokebrain.policy_dataset.audit import PolicyDatasetAuditor
from pokebrain.policy_dataset.diversity import PolicyDatasetDiversityReporter
from pokebrain.policy_dataset.features import FeatureExtractor
from pokebrain.policy_dataset.fingerprint import fingerprint_report
from pokebrain.policy_dataset.models import DatasetSplit, PolicyDatasetManifest, PolicyDatasetRecord
from pokebrain.policy_dataset.quality import DataQualityReporter
from pokebrain.policy_dataset.serialization import (
    audit_report_to_json,
    baseline_report_to_json,
    diversity_report_to_json,
    fingerprint_report_to_json,
    manifest_to_json,
    quality_report_to_json,
    write_json,
    write_records_jsonl,
)
from pokebrain.policy_dataset.splitter import PolicyDatasetSplitter


class PolicyDatasetBuilder:
    def __init__(
        self,
        *,
        feature_extractor: FeatureExtractor | None = None,
        baseline_evaluator: BaselineEvaluator | None = None,
        splitter: PolicyDatasetSplitter | None = None,
    ) -> None:
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.baseline_evaluator = baseline_evaluator or BaselineEvaluator()
        self.splitter = splitter or PolicyDatasetSplitter()

    def build(
        self,
        records: tuple[PolicyDatasetRecord, ...],
        *,
        dataset_version: str,
        parser_version: str,
        belief_version: str,
        output_dir: Path | None = None,
        generated_at: str | None = None,
    ) -> tuple[PolicyDatasetManifest, DatasetSplit]:
        filtered = tuple(record for record in records if _is_usable(record))
        featured = tuple(replace(record, features=self.feature_extractor.transform(record.example)) for record in filtered)
        split = self.splitter.split_by_battle_group(featured)
        manifest = PolicyDatasetManifest(
            dataset_version=dataset_version,
            generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
            parser_version=parser_version,
            belief_version=belief_version,
            feature_version=self.feature_extractor.schema.version,
            feature_count=self.feature_extractor.schema.feature_count,
            feature_names=self.feature_extractor.schema.feature_names,
            replay_count=len({record.metadata.replay_id for record in featured}),
            decision_count=len(featured),
            train_examples=len(split.train),
            validation_examples=len(split.validation),
            test_examples=len(split.test),
            data_start=min((record.metadata.upload_time for record in featured), default=None),
            data_end=max((record.metadata.upload_time for record in featured), default=None),
        )
        if output_dir is not None:
            self._write(output_dir, manifest, split, featured)
        return manifest, split

    def _write(
        self,
        output_dir: Path,
        manifest: PolicyDatasetManifest,
        split: DatasetSplit,
        all_records: tuple[PolicyDatasetRecord, ...],
    ) -> None:
        write_json(output_dir / "manifest.json", manifest_to_json(manifest))
        write_json(output_dir / "quality_report.json", quality_report_to_json(DataQualityReporter().report(all_records)))
        write_json(output_dir / "audit_report.json", audit_report_to_json(PolicyDatasetAuditor(self.feature_extractor).audit(all_records)))
        write_json(output_dir / "diversity_report.json", diversity_report_to_json(PolicyDatasetDiversityReporter().report(all_records)))
        write_json(output_dir / "fingerprint_report.json", fingerprint_report_to_json(fingerprint_report(all_records)))
        write_json(output_dir / "baseline_report.json", baseline_report_to_json(self.baseline_evaluator.evaluate(split.test or split.validation or split.train)))
        write_records_jsonl(output_dir / "authoritative" / "train.jsonl", split.train)
        write_records_jsonl(output_dir / "authoritative" / "validation.jsonl", split.validation)
        write_records_jsonl(output_dir / "authoritative" / "test.jsonl", split.test)
        (output_dir / "reconstructed_complete").mkdir(parents=True, exist_ok=True)
        (output_dir / "partial").mkdir(parents=True, exist_ok=True)


def temporal_split(
    records: tuple[PolicyDatasetRecord, ...],
    *,
    train_ratio: float = 0.7,
    validation_ratio: float = 0.15,
) -> DatasetSplit:
    ordered = tuple(sorted(records, key=lambda record: (record.metadata.upload_time, record.metadata.replay_id, record.metadata.turn_number)))
    total = len(ordered)
    train_end = int(total * train_ratio)
    validation_end = train_end + int(total * validation_ratio)
    return DatasetSplit(
        train=ordered[:train_end],
        validation=ordered[train_end:validation_end],
        test=ordered[validation_end:],
    )


def _is_usable(record: PolicyDatasetRecord) -> bool:
    return bool(record.example.legal_actions) and record.example.actual_action in record.example.legal_actions
