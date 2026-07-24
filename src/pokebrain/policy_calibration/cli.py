from __future__ import annotations

from pathlib import Path

from pokebrain.policy_calibration.pipeline import PolicyCalibrationPipeline
from pokebrain.policy_calibration.store import save_policy_profile


def evaluate_policy_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    rating_bucket: str | None = None,
) -> None:
    pipeline = PolicyCalibrationPipeline()
    examples = pipeline.examples_from_paths(replay_paths, format_id=format_id, rating_bucket=rating_bucket)
    metrics = pipeline.evaluate(examples)
    print(_render_metrics("Policy baseline", metrics))


def calibrate_policy_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    output_path: Path,
    rating_bucket: str | None = None,
) -> None:
    pipeline = PolicyCalibrationPipeline()
    examples = pipeline.examples_from_paths(replay_paths, format_id=format_id, rating_bucket=rating_bucket)
    split = pipeline.temporal_split(examples)
    baseline = pipeline.evaluate(split.validation or split.train)
    profile = pipeline.fit_profile(split.train or examples, format_id=format_id, rating_bucket=rating_bucket)
    calibrated_policy = pipeline._score_profile(
        split.validation or split.train or examples,
        weights=profile.weights,
        temperature=profile.calibration.temperature,
    )
    save_policy_profile(profile, output_path)
    print(f"Exemplos: {len(examples)}")
    print(f"Treino/validacao/teste: {len(split.train)}/{len(split.validation)}/{len(split.test)}")
    print("")
    print(_render_metrics("Baseline validation", baseline))
    print("")
    print(_render_metrics("Calibrated validation", calibrated_policy))
    print("")
    print(f"Perfil salvo em: {output_path}")


def _render_metrics(title: str, metrics) -> str:
    return "\n".join(
        (
            title,
            "-" * len(title),
            f"Examples: {metrics.examples}",
            f"Top-1: {metrics.top1_accuracy:.1%}",
            f"Top-3: {metrics.top3_coverage:.1%}",
            f"Top-4: {metrics.top4_coverage:.1%}",
            f"Actual probability: {metrics.actual_action_probability:.3f}",
            f"Log loss: {metrics.log_loss:.3f}",
            f"Brier score: {metrics.brier_score:.3f}",
            f"Entropy: {metrics.average_entropy:.3f}",
            f"Out of search: {metrics.out_of_search_rate:.1%}",
        )
    )
