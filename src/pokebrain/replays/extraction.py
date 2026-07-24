from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pokebrain.policy_calibration.pipeline import PolicyCalibrationPipeline
from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.replay.loader import ReplayLoader
from pokebrain.replays.catalog import ReplayCatalog
from pokebrain.replays.models import CatalogReplay, PolicyExampleMetadata, rating_bucket
from pokebrain.replays.public_parser import PublicReplayParser
from pokebrain.replays.storage import RawReplayStorage


@dataclass(slots=True)
class ExtractionReport:
    requested: int = 0
    parsed: int = 0
    examples: int = 0
    failed: int = 0


class PolicyExampleExtractionJob:
    def __init__(
        self,
        *,
        catalog: ReplayCatalog,
        storage: RawReplayStorage | None = None,
        pipeline: PolicyCalibrationPipeline | None = None,
        public_parser: PublicReplayParser | None = None,
    ) -> None:
        self.catalog = catalog
        self.storage = storage or RawReplayStorage()
        self.pipeline = pipeline or PolicyCalibrationPipeline()
        self.public_parser = public_parser or PublicReplayParser()

    def run(
        self,
        replay_ids: tuple[str, ...],
        parser_version: str,
        *,
        output_dir: Path | None = None,
        feature_version: str = "policy-features-v1",
        belief_model_version: str = "belief-v1",
    ) -> ExtractionReport:
        report = ExtractionReport(requested=len(replay_ids))
        output_dir = output_dir or Path("data/policy/examples")
        output_dir.mkdir(parents=True, exist_ok=True)
        for replay_id in replay_ids:
            item = self.catalog.get(replay_id)
            if item is None:
                report.failed += 1
                continue
            try:
                examples, partial_examples, statuses = self._examples_for(item)
                self._write_examples(
                    item,
                    examples,
                    partial_examples,
                    output_dir=output_dir,
                    parser_version=parser_version,
                    feature_version=feature_version,
                    belief_model_version=belief_model_version,
                )
                status_text = ",".join(status.value for status in statuses)
                if examples:
                    self.catalog.mark_parsed(replay_id, parser_version)
                elif partial_examples:
                    self.catalog.mark_parse_status(replay_id, parser_version, "partial", status_text)
                else:
                    self.catalog.mark_parse_failed(replay_id, parser_version, status_text or "no_examples")
                report.parsed += 1
                report.examples += len(examples) + len(partial_examples)
            except Exception as exc:
                self.catalog.mark_parse_failed(replay_id, parser_version, str(exc))
                report.failed += 1
        return report

    def run_pending(
        self,
        *,
        format_id: str,
        parser_version: str,
        status: str = "pending",
        limit: int | None = None,
        output_dir: Path | None = None,
    ) -> ExtractionReport:
        items = self.catalog.list_by_status(format_id=format_id, parse_status=status, limit=limit)
        return self.run(tuple(item.replay_id for item in items), parser_version, output_dir=output_dir)

    def _examples_for(self, item: CatalogReplay):
        payload = self.storage.load_payload(item.raw_path)
        local_artifact_dir = payload.get("local_artifact_dir")
        if local_artifact_dir:
            replay = ReplayLoader().load(Path(str(local_artifact_dir)))
            return self.pipeline.examples_from_replay(replay, format_id=item.format_id, rating_bucket=rating_bucket(item.rating)), (), ()
        raw_log = str(payload.get("log") or "")
        if raw_log:
            parsed = self.public_parser.parse(replay_id=item.replay_id, format_id=item.format_id, raw_log=raw_log)
            return parsed.training_examples, parsed.partial_examples, parsed.statuses
        raise ValueError("missing_replay_log")

    def _write_examples(
        self,
        item: CatalogReplay,
        examples,
        partial_examples,
        *,
        output_dir: Path,
        parser_version: str,
        feature_version: str,
        belief_model_version: str,
    ) -> None:
        path = output_dir / item.format_id / f"{item.replay_id}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            for example in examples:
                metadata = PolicyExampleMetadata(
                    replay_id=item.replay_id,
                    turn_number=example.observed_state.turn,
                    player_side="opponent",
                    format_id=item.format_id,
                    upload_time=item.upload_time,
                    rating_bucket=rating_bucket(item.rating),
                    parser_version=parser_version,
                    feature_version=feature_version,
                    belief_model_version=belief_model_version,
                )
                file.write(
                    json.dumps(
                        {
                            "metadata": asdict(metadata),
                            "actual_action": _action_to_json(example.actual_action),
                            "legal_actions": [_action_to_json(action) for action in example.legal_actions],
                            "predicted_actions": [
                                {
                                    "action": _action_to_json(item.action),
                                    "probability": item.probability,
                                    "policy_score": item.policy_score,
                                    "reasons": [
                                        {
                                            "code": reason.code,
                                            "contribution": reason.contribution,
                                            "description": reason.description,
                                        }
                                        for reason in item.reasons
                                    ],
                                }
                                for item in example.predicted_actions
                            ],
                        },
                        sort_keys=True,
                    )
                )
                file.write("\n")
            for example in partial_examples:
                metadata = PolicyExampleMetadata(
                    replay_id=item.replay_id,
                    turn_number=example.observed_state.turn,
                    player_side=example.actual_action.side,
                    format_id=item.format_id,
                    upload_time=item.upload_time,
                    rating_bucket=rating_bucket(item.rating),
                    parser_version=parser_version,
                    feature_version=feature_version,
                    belief_model_version=belief_model_version,
                )
                file.write(
                    json.dumps(
                        {
                            "metadata": asdict(metadata),
                            "partial": True,
                            "actual_action": _action_to_json(example.actual_action.action),
                            "candidate_actions": None if example.candidate_actions is None else [_action_to_json(action) for action in example.candidate_actions],
                            "missing_information": example.missing_information,
                        },
                        sort_keys=True,
                    )
                )
                file.write("\n")


def _action_to_json(action: BattleAction) -> dict[str, object]:
    if action.action_type is ActionType.MOVE:
        return {"type": "move", "move_id": action.move_id}
    return {"type": "switch", "switch_target_id": action.switch_target_id}
