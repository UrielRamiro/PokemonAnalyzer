from __future__ import annotations

from pathlib import Path

from pokebrain.policy_calibration.pipeline import PolicyCalibrationPipeline
from pokebrain.policy_dataset.audit import PolicyDatasetAuditor
from pokebrain.policy_dataset.builder import PolicyDatasetBuilder
from pokebrain.policy_dataset.diversity import PolicyDatasetDiversityReporter
from pokebrain.policy_dataset.fingerprint import fingerprint_report
from pokebrain.policy_dataset.quality import CoverageReporter, DataQualityReporter
from pokebrain.policy_dataset.serialization import audit_report_to_json, diversity_report_to_json, fingerprint_report_to_json, quality_report_to_json, write_json
from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.replay.loader import ReplayLoader
from pokebrain.replays.catalog import ReplayCatalog
from pokebrain.replays.models import PolicyExampleMetadata


def build_policy_dataset_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    output_dir: Path,
    dataset_version: str = "policy-dataset-v1",
    parser_version: str = "local-replay-loader-v1",
    belief_version: str = "belief-v1",
) -> None:
    records = _records_from_replays(replay_paths, format_id=format_id, parser_version=parser_version, belief_version=belief_version)
    manifest, split = PolicyDatasetBuilder().build(
        records,
        dataset_version=dataset_version,
        parser_version=parser_version,
        belief_version=belief_version,
        output_dir=output_dir,
    )
    print(f"Dataset: {manifest.dataset_version}")
    print(f"Decisoes: {manifest.decision_count}")
    print(f"Replays: {manifest.replay_count}")
    print(f"Treino/validacao/teste: {len(split.train)}/{len(split.validation)}/{len(split.test)}")
    print(f"Saida: {output_dir}")


def report_policy_dataset_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    output_path: Path | None = None,
) -> None:
    records = _records_from_replays(replay_paths, format_id=format_id, parser_version="local-replay-loader-v1", belief_version="belief-v1")
    report = DataQualityReporter().report(records)
    if output_path:
        write_json(output_path, quality_report_to_json(report))
    print(f"Total decisoes: {report.total_decisions}")
    print(f"Formatos: {report.by_format}")
    print(f"Turnos: {report.by_turn_bucket}")
    print(f"Acoes: {report.by_action_type}")
    print(f"Feature coverage: {report.feature_coverage}")


def report_policy_pilot_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    output_dir: Path | None = None,
) -> None:
    records = _records_from_replays(replay_paths, format_id=format_id, parser_version="local-replay-loader-v1", belief_version="belief-v1")
    diversity = PolicyDatasetDiversityReporter().report(records)
    fingerprints = fingerprint_report(records)
    audit = PolicyDatasetAuditor().audit(records)
    if output_dir:
        write_json(output_dir / "diversity_report.json", diversity_report_to_json(diversity))
        write_json(output_dir / "fingerprint_report.json", fingerprint_report_to_json(fingerprints))
        write_json(output_dir / "audit_report.json", audit_report_to_json(audit))
    print(f"Decisoes: {diversity.decisions}")
    print(f"Batalhas: {diversity.battles}")
    print(f"Times unicos: player={diversity.unique_player_teams} opponent={diversity.unique_opponent_teams}")
    print(f"Species unicas: {diversity.unique_species}")
    print(f"Fingerprints unicos: {fingerprints.unique_fingerprints}/{fingerprints.total_examples}")
    print(f"Duplicatas exatas: {fingerprints.exact_duplicates}")
    print(f"Estados iguais com acoes diferentes: {fingerprints.same_state_different_actions}")
    print(f"Auditoria: {'passou' if audit.passed else 'falhou'} ({audit.severe_violations} graves, {audit.warning_violations} avisos)")


def audit_policy_dataset_command(*, dataset_dir: Path) -> None:
    report_path = dataset_dir / "audit_report.json"
    if not report_path.exists():
        raise SystemExit(f"Audit report not found: {report_path}")
    import json

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    severe = int(payload.get("severe_violations", 0))
    warnings = int(payload.get("warning_violations", 0))
    print(f"Dataset: {dataset_dir}")
    print(f"Violacoes graves: {severe}")
    print(f"Avisos: {warnings}")
    if severe:
        raise SystemExit(1)


def coverage_policy_dataset_command(
    *,
    format_id: str,
    database_path: Path,
    output_path: Path | None = None,
) -> None:
    report = CoverageReporter().from_catalog(ReplayCatalog(database_path), format_id)
    payload = {
        "catalog_total": report.catalog_total,
        "complete_examples": report.complete_examples,
        "partial_examples": report.partial_examples,
        "status_counts": report.status_counts,
        "reason_counts": report.reason_counts,
    }
    if output_path:
        write_json(output_path, payload)
    print(f"Catalogo: {report.catalog_total}")
    print(f"Completos: {report.complete_examples}")
    print(f"Parciais: {report.partial_examples}")
    print(f"Status: {report.status_counts}")
    print(f"Razoes: {report.reason_counts}")


def _records_from_replays(
    replay_paths: tuple[Path, ...],
    *,
    format_id: str,
    parser_version: str,
    belief_version: str,
) -> tuple[PolicyDatasetRecord, ...]:
    pipeline = PolicyCalibrationPipeline()
    records: list[PolicyDatasetRecord] = []
    for replay_index, path in enumerate(sorted(replay_paths, key=lambda item: str(item)), start=1):
        replay = ReplayLoader().load(path)
        examples = pipeline.examples_from_replay(replay, format_id=format_id)
        for decision_index, example in enumerate(examples, start=1):
            records.append(
                PolicyDatasetRecord(
                    metadata=PolicyExampleMetadata(
                        replay_id=replay.battle_id,
                        turn_number=example.observed_state.turn,
                        player_side="opponent",
                        format_id=format_id,
                        upload_time=replay_index * 1_000_000 + decision_index,
                        rating_bucket=example.rating_bucket,
                        parser_version=parser_version,
                        feature_version="policy-features-v1",
                        belief_model_version=belief_version,
                    ),
                    example=example,
                )
            )
    return tuple(records)
