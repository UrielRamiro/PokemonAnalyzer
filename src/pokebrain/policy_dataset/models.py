from __future__ import annotations

from dataclasses import dataclass

from pokebrain.policy_calibration.models import PolicyCalibrationMetrics, PolicyTrainingExample
from pokebrain.replays.models import PolicyExampleMetadata


@dataclass(frozen=True, slots=True)
class FeatureSchema:
    version: str
    feature_names: tuple[str, ...]

    @property
    def feature_count(self) -> int:
        return len(self.feature_names)


@dataclass(frozen=True, slots=True)
class FeatureVector:
    schema_version: str
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PolicyDatasetRecord:
    metadata: PolicyExampleMetadata
    example: PolicyTrainingExample
    features: FeatureVector | None = None


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    train: tuple[PolicyDatasetRecord, ...]
    validation: tuple[PolicyDatasetRecord, ...]
    test: tuple[PolicyDatasetRecord, ...]


@dataclass(frozen=True, slots=True)
class PolicyDatasetManifest:
    dataset_version: str
    generated_at: str
    parser_version: str
    belief_version: str
    feature_version: str
    feature_count: int
    feature_names: tuple[str, ...]
    replay_count: int
    decision_count: int
    train_examples: int
    validation_examples: int
    test_examples: int
    data_start: int | None
    data_end: int | None


@dataclass(frozen=True, slots=True)
class CoverageReport:
    catalog_total: int
    complete_examples: int
    partial_examples: int
    status_counts: tuple[tuple[str, int], ...]
    reason_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class PolicyDatasetReport:
    total_decisions: int
    by_format: tuple[tuple[str, int], ...]
    by_turn_bucket: tuple[tuple[str, int], ...]
    by_action_type: tuple[tuple[str, int], ...]
    feature_coverage: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class BaselineReport:
    random: PolicyCalibrationMetrics
    frequency: PolicyCalibrationMetrics
    heuristic: PolicyCalibrationMetrics


@dataclass(frozen=True, slots=True)
class PolicyExampleFingerprint:
    format_id: str
    observable_state_hash: str
    actor_private_state_hash: str
    legal_actions_hash: str
    actual_action_id: str


@dataclass(frozen=True, slots=True)
class FingerprintReport:
    total_examples: int
    unique_fingerprints: int
    exact_duplicates: int
    same_state_different_actions: int


@dataclass(frozen=True, slots=True)
class AuditViolation:
    severity: str
    code: str
    replay_id: str
    turn_number: int
    message: str


@dataclass(frozen=True, slots=True)
class PolicyDatasetAuditReport:
    total_examples: int
    severe_violations: int
    warning_violations: int
    violations: tuple[AuditViolation, ...]

    @property
    def passed(self) -> bool:
        return self.severe_violations == 0


@dataclass(frozen=True, slots=True)
class PolicyDatasetDiversityReport:
    decisions: int
    battles: int
    unique_player_teams: int
    unique_opponent_teams: int
    unique_species: int
    unique_species_combinations: int
    by_turn_bucket: tuple[tuple[str, int], ...]
    by_legal_action_count: tuple[tuple[str, int], ...]
    by_action_type: tuple[tuple[str, int], ...]
    tera_available: int
    hazards_present: int
    weather_present: int
    terrain_present: int
    forced_switch_states: int
    choice_lock_states: int
    by_agent: tuple[tuple[str, int], ...]
