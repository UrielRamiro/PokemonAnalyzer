from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActivePokemonState, BattleAction, BattleSideState, BattleState
from pokebrain.battle.models import ActionType
from pokebrain.search import HeuristicOpponentPolicyModel, OpponentPolicyConfig
from pokebrain.team.models import EVSpread, PokemonSet


class OpponentPolicyModelTest(unittest.TestCase):
    def test_immediate_ko_receives_high_probability(self) -> None:
        policy = HeuristicOpponentPolicyModel(config=OpponentPolicyConfig(temperature=0.8))
        state = self._state(
            player=self._set("dragapult", ("shadowball",)),
            opponent=self._set("kingambit", ("suckerpunch", "swordsdance")),
            player_hp=20,
        )
        actions = (
            BattleAction(ActionType.MOVE, move_id="suckerpunch"),
            BattleAction(ActionType.MOVE, move_id="swordsdance"),
        )

        predicted = policy.predict(state, None, actions)

        self.assertEqual(predicted[0].action, BattleAction(ActionType.MOVE, move_id="suckerpunch"))
        self.assertGreater(predicted[0].probability, 0.8)

    def test_policy_probabilities_sum_to_one(self) -> None:
        predicted = HeuristicOpponentPolicyModel().predict(
            self._state(),
            None,
            (
                BattleAction(ActionType.MOVE, move_id="dracometeor"),
                BattleAction(ActionType.MOVE, move_id="uturn"),
                BattleAction(ActionType.SWITCH, switch_target_id="kingambit"),
            ),
        )

        self.assertAlmostEqual(sum(item.probability for item in predicted), 1.0)

    def test_illegal_actions_are_never_returned(self) -> None:
        legal = (BattleAction(ActionType.MOVE, move_id="dracometeor"),)

        predicted = HeuristicOpponentPolicyModel().predict(self._state(), None, legal)

        self.assertEqual(tuple(item.action for item in predicted), legal)

    def test_low_probability_tactical_threat_is_preserved(self) -> None:
        policy = HeuristicOpponentPolicyModel(config=OpponentPolicyConfig(maximum_actions=2, minimum_probability=0.4))
        state = self._state(
            player=self._set("dragapult", ("shadowball",)),
            opponent=self._set("kingambit", ("suckerpunch", "kowtowcleave", "swordsdance")),
            player_hp=20,
        )
        predicted = policy.predict(
            state,
            None,
            (
                BattleAction(ActionType.MOVE, move_id="kowtowcleave"),
                BattleAction(ActionType.MOVE, move_id="swordsdance"),
                BattleAction(ActionType.MOVE, move_id="suckerpunch"),
            ),
        )

        selected = policy.select_actions(predicted, maximum_actions=2)

        self.assertIn(BattleAction(ActionType.MOVE, move_id="suckerpunch"), tuple(item.action for item in selected))

    def test_policy_uses_only_observable_information(self) -> None:
        policy = HeuristicOpponentPolicyModel()
        observed = self._state(opponent=self._set("dragapult", ("shadowball", "uturn"), item_id=None))
        hidden_changed = self._state(opponent=self._set("dragapult", ("shadowball", "uturn"), item_id="choicespecs"))
        actions = (
            BattleAction(ActionType.MOVE, move_id="shadowball"),
            BattleAction(ActionType.MOVE, move_id="uturn"),
        )

        observed_policy = policy.predict(observed, None, actions)
        hidden_policy = policy.predict(hidden_changed, None, actions)

        self.assertEqual(
            tuple((item.action, item.probability) for item in observed_policy),
            tuple((item.action, item.probability) for item in hidden_policy),
        )

    def test_same_state_and_seed_produce_same_policy(self) -> None:
        policy = HeuristicOpponentPolicyModel()
        state = self._state()
        actions = (
            BattleAction(ActionType.MOVE, move_id="dracometeor"),
            BattleAction(ActionType.MOVE, move_id="shadowball"),
        )

        self.assertEqual(policy.predict(state, None, actions), policy.predict(state, None, actions))

    def test_scenario_changes_action_distribution(self) -> None:
        policy = HeuristicOpponentPolicyModel()
        shadowball_state = self._state(opponent=self._set("dragapult", ("shadowball", "uturn")))
        dragon_state = self._state(opponent=self._set("dragapult", ("dracometeor", "uturn")))

        shadowball_policy = policy.predict(
            shadowball_state,
            None,
            (BattleAction(ActionType.MOVE, move_id="shadowball"), BattleAction(ActionType.MOVE, move_id="uturn")),
        )
        dragon_policy = policy.predict(
            dragon_state,
            None,
            (BattleAction(ActionType.MOVE, move_id="dracometeor"), BattleAction(ActionType.MOVE, move_id="uturn")),
        )

        self.assertNotEqual(
            tuple(item.probability for item in shadowball_policy),
            tuple(item.probability for item in dragon_policy),
        )

    def _state(
        self,
        player: PokemonSet | None = None,
        opponent: PokemonSet | None = None,
        player_hp: int = 100,
    ) -> BattleState:
        player = player or self._set("greattusk", ("earthquake", "rapidspin"))
        opponent = opponent or self._set("dragapult", ("dracometeor", "shadowball", "uturn"))
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=1,
            player=BattleSideState(ActivePokemonState(player, player_hp), (player, self._set("kingambit", ("suckerpunch",)))),
            opponent=BattleSideState(ActivePokemonState(opponent, 100), (opponent, self._set("kingambit", ("suckerpunch",)))),
        )

    def _set(self, species_id: str, moves: tuple[str, ...], item_id: str | None = None) -> PokemonSet:
        return PokemonSet(
            species_id=species_id,
            nickname=None,
            item_id=item_id,
            ability_id=None,
            level=100,
            nature=None,
            tera_type=None,
            moves=moves,
            evs=EVSpread(),
        )


if __name__ == "__main__":
    unittest.main()
