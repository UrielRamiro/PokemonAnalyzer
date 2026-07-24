from __future__ import annotations

from pokebrain.policy_dataset.features import FeatureExtractor
from pokebrain.policy_dataset.fingerprint import fingerprint_record
from pokebrain.policy_dataset.models import AuditViolation, PolicyDatasetAuditReport, PolicyDatasetRecord


class PolicyDatasetAuditor:
    def __init__(self, feature_extractor: FeatureExtractor | None = None) -> None:
        self.feature_extractor = feature_extractor or FeatureExtractor()

    def audit(self, records: tuple[PolicyDatasetRecord, ...]) -> PolicyDatasetAuditReport:
        violations: list[AuditViolation] = []
        for record in records:
            if record.example.actual_action not in record.example.legal_actions:
                violations.append(_violation("severe", "actual_action_not_legal", record, "A acao real nao pertence as acoes legais."))
            if len(set(record.example.legal_actions)) != len(record.example.legal_actions):
                violations.append(_violation("severe", "duplicate_legal_actions", record, "Existem legal actions duplicadas."))
            first_features = self.feature_extractor.transform(record.example)
            second_features = self.feature_extractor.transform(record.example)
            if first_features != second_features:
                violations.append(_violation("severe", "features_not_deterministic", record, "As features mudaram entre duas execucoes iguais."))
            if fingerprint_record(record) != fingerprint_record(record):
                violations.append(_violation("severe", "fingerprint_not_stable", record, "O fingerprint mudou entre duas execucoes iguais."))
            if record.features is not None and record.features != first_features:
                violations.append(_violation("warning", "stored_features_outdated", record, "As features armazenadas diferem da versao atual do extrator."))
        severe = sum(1 for violation in violations if violation.severity == "severe")
        warnings = sum(1 for violation in violations if violation.severity == "warning")
        return PolicyDatasetAuditReport(
            total_examples=len(records),
            severe_violations=severe,
            warning_violations=warnings,
            violations=tuple(violations),
        )

    def assert_no_future_leakage(self, before: PolicyDatasetRecord, after_future_event: PolicyDatasetRecord) -> bool:
        before_features = self.feature_extractor.transform(before.example)
        after_features = self.feature_extractor.transform(after_future_event.example)
        return before_features == after_features


def _violation(severity: str, code: str, record: PolicyDatasetRecord, message: str) -> AuditViolation:
    return AuditViolation(
        severity=severity,
        code=code,
        replay_id=record.metadata.replay_id,
        turn_number=record.metadata.turn_number,
        message=message,
    )
