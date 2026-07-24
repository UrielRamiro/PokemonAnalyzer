from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActionType, ActivePokemonState, BattleAction, BattleSideState, BattleState
from pokebrain.belief.models import BeliefState
from pokebrain.policy_calibration import PolicyCalibrationEvaluator, PolicyCalibrationPipeline
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_calibration.store import load_policy_profile, save_policy_profile
from pokebrain.replay.loader import ReplayLoader
from pokebrain.search import HeuristicOpponentPolicyModel, OpponentPolicyConfig, PolicyCalibration, PolicyProfile, PolicyWeights, WeightedAction
from pokebrain.team.models import EVSpread, PokemonSet


class PolicyCalibrationTest(unittest.TestCase):
    def test_evaluates_policy_metrics(self) -> None:
        actual = BattleAction(ActionType.MOVE, move_id="shadowball")
        example = PolicyTrainingExample(
            format_id="gen9ou",
            rating_bucket=None,
            observed_state=self._state(),
            belief_state=BeliefState(opponent_team=()),
            legal_actions=(actual, BattleAction(ActionType.MOVE, move_id="uturn")),
            predicted_actions=(
                WeightedAction(actual, 0.7, 1.0),
                WeightedAction(BattleAction(ActionType.MOVE, move_id="uturn"), 0.3, 0.0),
            ),
            actual_action=actual,
        )

        metrics = PolicyCalibrationEvaluator().evaluate((example,))

        self.assertEqual(metrics.examples, 1)
        self.assertEqual(metrics.top1_accuracy, 1.0)
        self.assertEqual(metrics.top3_coverage, 1.0)
        self.assertAlmostEqual(metrics.actual_action_probability, 0.7)
        self.assertGreater(metrics.average_entropy, 0)

    def test_pipeline_extracts_examples_from_local_replay(self) -> None:
        replay_path = ROOT_DIR / "runs" / "2026-07-20" / "benchmark-20260720014317-00001"
        replay = ReplayLoader().load(replay_path)

        examples = PolicyCalibrationPipeline().examples_from_replay(replay, format_id="gen9ou")

        self.assertTrue(examples)
        self.assertTrue(all(example.actual_action in example.legal_actions for example in examples))
        self.assertTrue(all(example.predicted_actions for example in examples))

    def test_temperature_fit_can_reduce_validation_log_loss(self) -> None:
        pipeline = PolicyCalibrationPipeline(policy_config=OpponentPolicyConfig(temperature=0.8))
        state = self._state(
            player=self._set("dragapult", ("shadowball",)),
            opponent=self._set("kingambit", ("suckerpunch", "swordsdance")),
            player_hp=20,
        )
        actions = (
            BattleAction(ActionType.MOVE, move_id="suckerpunch"),
            BattleAction(ActionType.MOVE, move_id="swordsdance"),
        )
        actual = BattleAction(ActionType.MOVE, move_id="swordsdance")
        policy = HeuristicOpponentPolicyModel(config=OpponentPolicyConfig(temperature=0.8))
        example = PolicyTrainingExample(
            format_id="gen9ou",
            rating_bucket=None,
            observed_state=state,
            belief_state=BeliefState(opponent_team=()),
            legal_actions=actions,
            predicted_actions=policy.predict(state, None, actions),
            actual_action=actual,
        )
        baseline = pipeline.evaluate((example,)).log_loss

        temperature = pipeline.fit_temperature((example,), PolicyWeights(), (0.8, 1.6, 2.0))
        fitted = pipeline._score_profile((example,), weights=PolicyWeights(), temperature=temperature).log_loss

        self.assertLessEqual(fitted, baseline)

    def test_profile_store_roundtrip(self) -> None:
        profile = PolicyProfile(
            format_id="gen9ou",
            rating_bucket="high",
            weights=replace(PolicyWeights(), expected_damage=2.5),
            calibration=PolicyCalibration(temperature=1.25, probability_floor=0.03, tactical_threat_floor=0.01),
        )
        path = ROOT_DIR / "data" / "policy_profiles" / "test_profile_roundtrip.json"
        save_policy_profile(profile, path)
        loaded = load_policy_profile(path)
        path.unlink()

        self.assertEqual(loaded, profile)

    def _state(
        self,
        player: PokemonSet | None = None,
        opponent: PokemonSet | None = None,
        player_hp: int = 100,
    ) -> BattleState:
        player = player or self._set("greattusk", ("earthquake", "rapidspin"))
        opponent = opponent or self._set("dragapult", ("shadowball", "uturn"))
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=1,
            player=BattleSideState(ActivePokemonState(player, player_hp), (player,)),
            opponent=BattleSideState(ActivePokemonState(opponent, 100), (opponent, self._set("kingambit", ("suckerpunch",)))),
        )

    def _set(self, species_id: str, moves: tuple[str, ...]) -> PokemonSet:
        return PokemonSet(
            species_id=species_id,
            nickname=None,
            item_id=None,
            ability_id=None,
            level=100,
            nature=None,
            tera_type=None,
            moves=moves,
            evs=EVSpread(),
        )


if __name__ == "__main__":
    unittest.main()
