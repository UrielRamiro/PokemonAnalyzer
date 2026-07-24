from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActionType, ActivePokemonState, BattleAction, BattleSideState, BattleState
from pokebrain.belief.models import BeliefState
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_dataset.audit import PolicyDatasetAuditor
from pokebrain.policy_dataset.builder import PolicyDatasetBuilder
from pokebrain.policy_dataset.diversity import PolicyDatasetDiversityReporter
from pokebrain.policy_dataset.fingerprint import fingerprint_record, fingerprint_report
from pokebrain.policy_dataset.models import PolicyDatasetRecord
from pokebrain.policy_dataset.splitter import PolicyDatasetSplitter
from pokebrain.replays.models import PolicyExampleMetadata
from pokebrain.search.policy import WeightedAction
from pokebrain.team.models import EVSpread, PokemonSet


class PolicyDatasetPilotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT_DIR / ".tmp_tests" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_fingerprints_count_exact_duplicates_and_action_ambiguity(self) -> None:
        first = self._record("battle-1", 1, actual=self._move("earthquake"))
        duplicate = self._record("battle-1-copy", 1, actual=self._move("earthquake"))
        ambiguous = self._record("battle-1-alt", 1, actual=self._move("stealthrock"))

        report = fingerprint_report((first, duplicate, ambiguous))

        self.assertEqual(report.total_examples, 3)
        self.assertEqual(report.unique_fingerprints, 2)
        self.assertEqual(report.exact_duplicates, 1)
        self.assertEqual(report.same_state_different_actions, 1)
        self.assertEqual(fingerprint_record(first), fingerprint_record(duplicate))

    def test_splitter_keeps_battle_turns_in_only_one_split(self) -> None:
        records = tuple(
            self._record(f"battle-{battle}", turn, upload_time=battle * 100 + turn)
            for battle in range(10)
            for turn in (1, 2)
        )

        split = PolicyDatasetSplitter().split_by_battle_group(records)

        train = {record.metadata.replay_id for record in split.train}
        validation = {record.metadata.replay_id for record in split.validation}
        test = {record.metadata.replay_id for record in split.test}
        self.assertFalse(train & validation)
        self.assertFalse(train & test)
        self.assertFalse(validation & test)
        self.assertEqual(len(train), 7)
        self.assertEqual(len(validation), 1)
        self.assertEqual(len(test), 2)

    def test_audit_reports_severe_violations_for_illegal_actual_action(self) -> None:
        record = self._record("battle-1", 1, actual=BattleAction(ActionType.MOVE, move_id="dracometeor"), include_actual=False)

        report = PolicyDatasetAuditor().audit((record,))

        self.assertFalse(report.passed)
        self.assertEqual(report.severe_violations, 1)
        self.assertEqual(report.violations[0].code, "actual_action_not_legal")

    def test_diversity_report_measures_pilot_shape(self) -> None:
        records = (
            self._record("battle-1", 1, hazards=True, weather="RainDance"),
            self._record("battle-1", 6, actual=self._switch("kingambit"), hazards=True),
            self._record("battle-2", 21, opponent_item="choicescarf"),
        )

        report = PolicyDatasetDiversityReporter().report(records)

        self.assertEqual(report.decisions, 3)
        self.assertEqual(report.battles, 2)
        self.assertEqual(report.hazards_present, 2)
        self.assertEqual(report.weather_present, 1)
        self.assertEqual(report.choice_lock_states, 1)
        self.assertIn(("unknown", 3), report.by_agent)

    def test_builder_writes_pilot_integrity_reports(self) -> None:
        output = self.root / "pilot"
        records = tuple(self._record(f"battle-{index}", index, upload_time=index) for index in range(5))

        manifest, split = PolicyDatasetBuilder().build(
            records,
            dataset_version="policy-dataset-pilot-1",
            parser_version="parser-v1",
            belief_version="belief-v1",
            output_dir=output,
            generated_at="2026-07-20T00:00:00+00:00",
        )

        self.assertEqual(manifest.dataset_version, "policy-dataset-pilot-1")
        self.assertEqual(manifest.decision_count, 5)
        self.assertEqual((len(split.train), len(split.validation), len(split.test)), (3, 0, 2))
        self.assertTrue((output / "audit_report.json").exists())
        self.assertTrue((output / "diversity_report.json").exists())
        self.assertTrue((output / "fingerprint_report.json").exists())

    def test_future_events_do_not_change_past_features(self) -> None:
        before = self._record("battle-1", 1, opponent_item=None, opponent_moves=("earthquake",))
        after_future_reveal = self._record(
            "battle-1",
            1,
            opponent_item=None,
            opponent_moves=("earthquake",),
            hidden_future_item="leftovers",
            hidden_future_move="fireblast",
            hidden_future_tera="Fire",
            hidden_future_species="dragapult",
        )

        self.assertTrue(PolicyDatasetAuditor().assert_no_future_leakage(before, after_future_reveal))

    def _record(
        self,
        replay_id: str,
        turn: int,
        *,
        upload_time: int | None = None,
        actual: BattleAction | None = None,
        include_actual: bool = True,
        hazards: bool = False,
        weather: str | None = None,
        opponent_item: str | None = None,
        opponent_moves: tuple[str, ...] = ("earthquake",),
        hidden_future_item: str | None = None,
        hidden_future_move: str | None = None,
        hidden_future_tera: str | None = None,
        hidden_future_species: str | None = None,
    ) -> PolicyDatasetRecord:
        actual = actual or self._move("earthquake")
        legal_actions = (
            self._move("earthquake"),
            self._move("stealthrock"),
            self._switch("kingambit"),
        )
        if include_actual and actual not in legal_actions:
            legal_actions = (*legal_actions, actual)
        predicted = tuple(WeightedAction(action, 1 / len(legal_actions), 0.0) for action in legal_actions)
        example = PolicyTrainingExample(
            format_id="gen9ou",
            rating_bucket=None,
            observed_state=self._state(
                turn=turn,
                hazards=hazards,
                weather=weather,
                opponent_item=opponent_item,
                opponent_moves=opponent_moves,
            ),
            belief_state=BeliefState(opponent_team=()),
            legal_actions=legal_actions,
            predicted_actions=predicted,
            actual_action=actual,
        )
        _ = (hidden_future_item, hidden_future_move, hidden_future_tera, hidden_future_species)
        return PolicyDatasetRecord(
            metadata=PolicyExampleMetadata(
                replay_id=replay_id,
                turn_number=turn,
                player_side="p1",
                format_id="gen9ou",
                upload_time=upload_time or turn,
                rating_bucket=None,
                parser_version="parser-v1",
                feature_version="policy-features-v1",
                belief_model_version="belief-v1",
            ),
            example=example,
        )

    def _state(
        self,
        *,
        turn: int,
        hazards: bool,
        weather: str | None,
        opponent_item: str | None,
        opponent_moves: tuple[str, ...],
    ) -> BattleState:
        player = PokemonSet("dragapult", None, "choicespecs", None, 100, None, "Ghost", ("shadowball",), EVSpread())
        opponent = PokemonSet("garchomp", None, opponent_item, None, 100, None, "Ground", opponent_moves, EVSpread())
        kingambit = PokemonSet("kingambit", None, None, None, 100, None, "Dark", (), EVSpread())
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=turn,
            player=BattleSideState(ActivePokemonState(player, 80), (player,), stealth_rock=hazards),
            opponent=BattleSideState(ActivePokemonState(opponent, 100), (opponent, kingambit), stealth_rock=hazards),
            weather=weather,
        )

    def _move(self, move_id: str) -> BattleAction:
        return BattleAction(ActionType.MOVE, move_id=move_id)

    def _switch(self, target_id: str) -> BattleAction:
        return BattleAction(ActionType.SWITCH, switch_target_id=target_id)


if __name__ == "__main__":
    unittest.main()
