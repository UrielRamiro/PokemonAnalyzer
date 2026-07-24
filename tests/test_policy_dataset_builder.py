from __future__ import annotations

import json
import shutil
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActionType, ActivePokemonState, BattleAction, BattleSideState, BattleState
from pokebrain.belief.models import BeliefState
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_dataset.baselines import BaselineEvaluator
from pokebrain.policy_dataset.builder import PolicyDatasetBuilder, temporal_split
from pokebrain.policy_dataset.features import FeatureExtractor
from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.policy_dataset.quality import CoverageReporter, DataQualityReporter
from pokebrain.policy_dataset.serialization import record_to_json
from pokebrain.replays.catalog import ReplayCatalog
from pokebrain.replays.models import PolicyExampleMetadata, RawReplay, ReplaySummary
from pokebrain.replays.storage import RawReplayStorage
from pokebrain.search.policy import WeightedAction
from pokebrain.team.models import EVSpread, PokemonSet


class PolicyDatasetBuilderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT_DIR / ".tmp_tests" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_manifest_is_reproducible_with_versions(self) -> None:
        records = tuple(self._record(index, upload_time=100 + index) for index in range(10))

        manifest_a, split_a = PolicyDatasetBuilder().build(
            records,
            dataset_version="test-v1",
            parser_version="parser-v1",
            belief_version="belief-v1",
            generated_at="2026-07-20T00:00:00+00:00",
        )
        manifest_b, split_b = PolicyDatasetBuilder().build(
            records,
            dataset_version="test-v1",
            parser_version="parser-v1",
            belief_version="belief-v1",
            generated_at="2026-07-20T00:00:00+00:00",
        )

        self.assertEqual(manifest_a, manifest_b)
        self.assertEqual(manifest_a.feature_version, "policy-features-v1")
        self.assertEqual(manifest_a.decision_count, 10)
        self.assertEqual((len(split_a.train), len(split_a.validation), len(split_a.test)), (7, 1, 2))
        self.assertEqual(split_a, split_b)

    def test_feature_extractor_is_deterministic_and_uses_observed_state_only(self) -> None:
        record = self._record(1, upload_time=10)
        hidden_changed = self._record(1, upload_time=10, opponent_hidden_moves=("shadowball", "uturn", "dracometeor", "flamethrower"))

        first = FeatureExtractor().transform(record.example)
        second = FeatureExtractor().transform(record.example)
        changed = FeatureExtractor().transform(hidden_changed.example)

        self.assertEqual(first, second)
        self.assertEqual(first, changed)
        self.assertEqual(len(first.values), FeatureExtractor().schema.feature_count)

    def test_temporal_split_uses_upload_time_order(self) -> None:
        records = (self._record(1, 300), self._record(2, 100), self._record(3, 200), self._record(4, 400))

        split = temporal_split(records, train_ratio=0.5, validation_ratio=0.25)

        self.assertEqual(tuple(record.metadata.upload_time for record in split.train), (100, 200))
        self.assertEqual(tuple(record.metadata.upload_time for record in split.validation), (300,))
        self.assertEqual(tuple(record.metadata.upload_time for record in split.test), (400,))

    def test_quality_report_summarizes_dataset(self) -> None:
        records = (
            self._record(1, 100, turn=1, actual=BattleAction(ActionType.MOVE, move_id="earthquake")),
            self._record(2, 200, turn=8, actual=BattleAction(ActionType.SWITCH, switch_target_id="kingambit")),
            self._record(3, 300, turn=21, actual=BattleAction(ActionType.MOVE, move_id="swordsdance")),
        )

        report = DataQualityReporter().report(records)

        self.assertEqual(report.total_decisions, 3)
        self.assertIn(("gen9ou", 3), report.by_format)
        self.assertIn(("turns_1_5", 1), report.by_turn_bucket)
        self.assertIn(("switch", 1), report.by_action_type)
        self.assertTrue(dict(report.feature_coverage)["hp_known"] > 0)

    def test_coverage_report_reads_catalog_statuses(self) -> None:
        catalog = ReplayCatalog(self.root / "replays.db")
        storage = RawReplayStorage(self.root / "raw")
        summary = ReplaySummary("r1", "gen9ou", 100, 1500, ("a", "b"))
        raw = RawReplay("r1", {"log": "|turn|1"}, datetime.now(timezone.utc), "sha", raw_text="")
        catalog.save_success(summary, raw, storage.save(summary, raw))
        catalog.mark_parse_status("r1", "parser-v1", "partial", "partial_missing_team")

        report = CoverageReporter().from_catalog(catalog, "gen9ou")

        self.assertEqual(report.catalog_total, 1)
        self.assertEqual(report.partial_examples, 1)
        self.assertIn(("partial_missing_team", 1), report.reason_counts)

    def test_baselines_return_metrics(self) -> None:
        report = BaselineEvaluator().evaluate(tuple(self._record(index, index) for index in range(3)))

        self.assertEqual(report.random.examples, 3)
        self.assertEqual(report.frequency.examples, 3)
        self.assertEqual(report.heuristic.examples, 3)

    def test_builder_writes_golden_dataset_outputs_deterministically(self) -> None:
        records = tuple(self._record(index, upload_time=100 + index) for index in range(5))
        output = self.root / "dataset"

        manifest, _split = PolicyDatasetBuilder().build(
            records,
            dataset_version="golden-v1",
            parser_version="parser-v1",
            belief_version="belief-v1",
            generated_at="2026-07-20T00:00:00+00:00",
            output_dir=output,
        )
        manifest_payload = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        first_record = (output / "authoritative" / "train.jsonl").read_text(encoding="utf-8").splitlines()[0]

        self.assertEqual(manifest_payload["dataset_version"], manifest.dataset_version)
        expected_record = temporal_split(tuple(self._record(index, upload_time=100 + index) for index in range(5))).train[0]
        expected_record = replace(expected_record, features=FeatureExtractor().transform(expected_record.example))
        self.assertEqual(json.loads(first_record), record_to_json(expected_record))
        self.assertTrue((output / "quality_report.json").exists())
        self.assertTrue((output / "baseline_report.json").exists())

    def _record(
        self,
        index: int,
        upload_time: int,
        *,
        turn: int = 1,
        actual: BattleAction | None = None,
        opponent_hidden_moves: tuple[str, ...] = (),
    ) -> PolicyDatasetRecord:
        actual = actual or BattleAction(ActionType.MOVE, move_id="earthquake")
        legal_actions = (
            BattleAction(ActionType.MOVE, move_id="earthquake"),
            BattleAction(ActionType.MOVE, move_id="stealthrock"),
            BattleAction(ActionType.SWITCH, switch_target_id="kingambit"),
        )
        if actual not in legal_actions:
            legal_actions = (*legal_actions, actual)
        predicted = tuple(WeightedAction(action, 1 / len(legal_actions), 0.0) for action in legal_actions)
        example = PolicyTrainingExample(
            format_id="gen9ou",
            rating_bucket=None,
            observed_state=self._state(turn=turn, opponent_hidden_moves=opponent_hidden_moves),
            belief_state=BeliefState(opponent_team=()),
            legal_actions=legal_actions,
            predicted_actions=predicted,
            actual_action=actual,
        )
        return PolicyDatasetRecord(
            metadata=PolicyExampleMetadata(
                replay_id=f"replay-{index}",
                turn_number=turn,
                player_side="p1",
                format_id="gen9ou",
                upload_time=upload_time,
                rating_bucket=None,
                parser_version="parser-v1",
                feature_version="policy-features-v1",
                belief_model_version="belief-v1",
            ),
            example=example,
        )

    def _state(self, *, turn: int, opponent_hidden_moves: tuple[str, ...]) -> BattleState:
        player = PokemonSet("dragapult", None, None, None, 100, None, None, ("shadowball",), EVSpread())
        opponent = PokemonSet("garchomp", None, None, None, 100, None, None, (), EVSpread())
        # The hidden argument intentionally does not enter the observed state.
        _ = opponent_hidden_moves
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=turn,
            player=BattleSideState(ActivePokemonState(player, 80), (player,)),
            opponent=BattleSideState(ActivePokemonState(opponent, 100), (opponent, PokemonSet("kingambit", None, None, None, 100, None, None, (), EVSpread()))),
        )


if __name__ == "__main__":
    unittest.main()
