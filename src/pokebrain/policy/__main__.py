from __future__ import annotations

import argparse
from pathlib import Path

from pokebrain.battles.config import load_generation_plan
from pokebrain.battles.ledger import BattleCampaignLedger
from pokebrain.battles.models import BattleJobStatus
from pokebrain.policy_dataset.cli import audit_policy_dataset_command, build_policy_dataset_command
from pokebrain.policy_evaluation.cli import evaluate_policy_baselines_command


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m pokebrain.policy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Fail if a built policy dataset has severe audit violations.")
    audit_parser.add_argument("--dataset", required=True)

    build_parser = subparsers.add_parser("build", help="Build a policy dataset from completed campaign artifacts.")
    build_parser.add_argument("--campaign", required=True)
    build_parser.add_argument("--dataset", required=True)
    build_parser.add_argument("--format", default="gen9ou")
    build_parser.add_argument("--artifact-root", default="battles")
    build_parser.add_argument("--config")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate baselines from completed campaign artifacts.")
    evaluate_parser.add_argument("--campaign", required=True)
    evaluate_parser.add_argument("--format", default="gen9ou")
    evaluate_parser.add_argument("--artifact-root", default="battles")
    evaluate_parser.add_argument("--config")
    evaluate_parser.add_argument("--output", required=True)
    evaluate_parser.add_argument("--dataset")

    args = parser.parse_args()
    if args.command == "audit":
        audit_policy_dataset_command(dataset_dir=Path(args.dataset))
    elif args.command == "build":
        build_policy_dataset_command(
            replay_paths=_campaign_replay_paths(Path(args.artifact_root), args.campaign, config_path=Path(args.config) if args.config else None),
            format_id=args.format,
            output_dir=Path(args.dataset),
            dataset_version=Path(args.dataset).name,
            parser_version="local-replay-loader-v1",
            belief_version="belief-v1",
        )
    elif args.command == "evaluate":
        evaluate_policy_baselines_command(
            replay_paths=_campaign_replay_paths(Path(args.artifact_root), args.campaign, config_path=Path(args.config) if args.config else None),
            format_id=args.format,
            output_dir=Path(args.output),
            dataset_dir=Path(args.dataset) if args.dataset else None,
        )


def _campaign_replay_paths(artifact_root: Path, campaign_id: str, *, config_path: Path | None = None) -> tuple[Path, ...]:
    campaign_dir = artifact_root / campaign_id
    completed = _completed_artifact_paths(campaign_id, config_path)
    if completed:
        paths = completed
    else:
        paths = tuple(path for path in sorted(campaign_dir.iterdir()) if path.is_dir() and (path / "battle.json").exists())
    if not paths:
        raise SystemExit(f"No completed campaign artifacts found in {campaign_dir}")
    return paths


def _completed_artifact_paths(campaign_id: str, config_path: Path | None) -> tuple[Path, ...]:
    resolved_config = config_path or Path("campaigns") / f"{campaign_id}.yaml"
    if not resolved_config.exists():
        return ()
    plan = load_generation_plan(resolved_config)
    records = BattleCampaignLedger(plan.database_path).list_jobs(campaign_id)
    return tuple(
        Path(record.artifact_path)
        for record in records
        if record.status is BattleJobStatus.COMPLETED and record.artifact_path
    )


if __name__ == "__main__":
    main()
