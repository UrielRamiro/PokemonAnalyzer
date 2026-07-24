from __future__ import annotations

import json
from pathlib import Path

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.policy_dataset.cli import _records_from_replays
from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.replays.models import PolicyExampleMetadata
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.belief.models import BeliefState
from pokebrain.battle.models import ActivePokemonState, BattleSideState, BattleState
from pokebrain.team.models import EVSpread, PokemonSet
from pokebrain.policy_evaluation.comparison import PolicyComparisonRunner
from pokebrain.policy_evaluation.predictors import ActiveSpeciesFrequencyPolicyPredictor, FrequencyPolicyPredictor, HeuristicPolicyPredictor, RandomPolicyPredictor
from pokebrain.policy_evaluation.runner import PolicyEvaluationRunner
from pokebrain.policy_evaluation.serialization import comparison_to_json, report_to_json, write_json


def evaluate_policy_baselines_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    output_dir: Path | None = None,
    dataset_dir: Path | None = None,
) -> None:
    records = _records_from_dataset(dataset_dir, format_id=format_id) if dataset_dir else _records_from_replays(replay_paths, format_id=format_id, parser_version="local-replay-loader-v1", belief_version="belief-v1")
    examples = tuple(record.example for record in records)
    predictors = [
        RandomPolicyPredictor(),
        FrequencyPolicyPredictor(examples),
    ]
    if not dataset_dir:
        predictors.append(ActiveSpeciesFrequencyPolicyPredictor(examples))
        predictors.append(HeuristicPolicyPredictor())
    bootstrap_iterations = 0 if dataset_dir else 200
    reports = tuple(
        PolicyEvaluationRunner().evaluate(predictor, records, bootstrap_iterations=bootstrap_iterations)
        for predictor in predictors
    )
    if output_dir is not None:
        for report in reports:
            write_json(output_dir / f"{report.summary.model_name}.json", report_to_json(report))
    for report in reports:
        summary = report.summary
        print(
            f"{summary.model_name}: examples={summary.examples} "
            f"top1={summary.top1_accuracy:.1%} top3={summary.top3_coverage:.1%} "
            f"log_loss={summary.log_loss:.3f} ece={summary.expected_calibration_error:.3f} "
            f"p95_ms={summary.p95_inference_ms:.3f}"
        )
    if dataset_dir:
        print("frequency-active-species: skipped for --dataset fast path; run without --dataset for full replay-based evaluation.")
        print("heuristic-v3: skipped for --dataset fast path; run without --dataset for full replay-based evaluation.")


def compare_policy_baselines_command(
    *,
    replay_paths: tuple[Path, ...],
    format_id: str,
    output_dir: Path | None = None,
) -> None:
    records = _records_from_replays(replay_paths, format_id=format_id, parser_version="local-replay-loader-v1", belief_version="belief-v1")
    examples = tuple(record.example for record in records)
    baseline, candidate, comparison = PolicyComparisonRunner().compare(
        baseline=FrequencyPolicyPredictor(examples),
        candidate=HeuristicPolicyPredictor(),
        records=records,
    )
    if output_dir is not None:
        write_json(output_dir / "baseline_frequency.json", report_to_json(baseline))
        write_json(output_dir / "candidate_heuristic-v3.json", report_to_json(candidate))
        write_json(output_dir / "comparison.json", comparison_to_json(comparison))
    print(f"{comparison.baseline_name} -> {comparison.candidate_name}")
    print(f"Top1 delta: {comparison.top1_delta:.1%}")
    print(f"Top3 delta: {comparison.top3_delta:.1%}")
    print(f"Log loss delta: {comparison.log_loss_delta:.3f}")
    print(f"ECE delta: {comparison.ece_delta:.3f}")
    print(f"Possivel regressao: {'sim' if comparison.likely_regression else 'nao'}")


def _records_from_dataset(dataset_dir: Path | None, *, format_id: str) -> tuple[PolicyDatasetRecord, ...]:
    if dataset_dir is None:
        return ()
    records: list[PolicyDatasetRecord] = []
    for split_name in ("train", "validation", "test"):
        path = dataset_dir / "authoritative" / f"{split_name}.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    records.append(_record_from_json(json.loads(line), format_id=format_id))
    if not records:
        raise SystemExit(f"No dataset records found in {dataset_dir}")
    return tuple(records)


def _record_from_json(payload: dict, *, format_id: str) -> PolicyDatasetRecord:
    metadata = PolicyExampleMetadata(**payload["metadata"])
    legal_actions = tuple(_action_from_json(action) for action in payload.get("legal_actions", ()))
    actual_action = _action_from_json(payload["actual_action"])
    example = PolicyTrainingExample(
        format_id=format_id,
        rating_bucket=metadata.rating_bucket,
        observed_state=_minimal_state(format_id),
        belief_state=BeliefState(opponent_team=()),
        legal_actions=legal_actions,
        predicted_actions=(),
        actual_action=actual_action,
    )
    return PolicyDatasetRecord(metadata=metadata, example=example)


def _action_from_json(payload: dict) -> BattleAction:
    if payload.get("type") == "switch":
        return BattleAction(ActionType.SWITCH, switch_target_id=payload.get("switch_target_id"), action_id=payload.get("action_id"))
    return BattleAction(ActionType.MOVE, move_id=payload.get("move_id"), action_id=payload.get("action_id"))


def _minimal_state(format_id: str) -> BattleState:
    placeholder = PokemonSet(
        species_id="unknown",
        nickname=None,
        item_id=None,
        ability_id=None,
        level=50,
        nature=None,
        tera_type=None,
        moves=(),
        evs=EVSpread(),
    )
    active = ActivePokemonState(set_data=placeholder, current_hp=100)
    side = BattleSideState(active=active, team=(placeholder,))
    return BattleState(generation=9, format_id=format_id, turn=0, player=side, opponent=side)
