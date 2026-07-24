from __future__ import annotations

from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.policy_evaluation.metrics import evaluate_predictions
from pokebrain.policy_evaluation.models import PolicyEvaluationReport, PolicyPredictor


class PolicyEvaluationRunner:
    def evaluate(
        self,
        predictor: PolicyPredictor,
        records: tuple[PolicyDatasetRecord, ...],
        *,
        bootstrap_iterations: int = 200,
    ) -> PolicyEvaluationReport:
        predictions = tuple(predictor.predict(record.example) for record in records)
        return evaluate_predictions(predictor.name, records, predictions, bootstrap_iterations=bootstrap_iterations)

    def evaluate_predictions(
        self,
        model_name: str,
        records: tuple[PolicyDatasetRecord, ...],
        predictions,
        *,
        bootstrap_iterations: int = 200,
    ) -> PolicyEvaluationReport:
        return evaluate_predictions(model_name, records, tuple(predictions), bootstrap_iterations=bootstrap_iterations)
