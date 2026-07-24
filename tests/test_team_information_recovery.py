from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.replay.loader import ReplayLoader
from pokebrain.replays.legal_differential import LegalActionDifferentialValidator
from pokebrain.replays.legal_recovery import RecoveredLegalActionGenerator
from pokebrain.replays.public_models import PartialPolicyExample
from pokebrain.replays.public_parser import PublicReplayParser
from pokebrain.replays.recovery_models import (
    EvidenceConfidence,
    EvidenceSource,
    EvidenceValue,
    HypothesizedMoveSet,
    LegalActionQuality,
    ReplayArtifactBundle,
    ResolvedPokemon,
    ResolvedTeam,
    WeightedMoveSet,
)
from pokebrain.replays.recovery_pipeline import TeamInformationRecoveryPipeline
from pokebrain.replays.team_recovery import TeamEvidenceResolver
from pokebrain.replays.training_builder import PolicyTrainingExampleBuilder
from pokebrain.team.models import EVSpread, PokemonSet, Team


class TeamInformationRecoveryTest(unittest.TestCase):
    def test_team_export_generates_complete_actor_legal_actions(self) -> None:
        parsed = self._parsed()
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._artifacts())

        legal = RecoveredLegalActionGenerator().generate(
            state=parsed.partial_examples[0].observed_state,
            actor_side="p1",
            actor_team=resolution.player_1_team,
        )

        self.assertEqual(legal.quality, LegalActionQuality.RECONSTRUCTED_COMPLETE)
        self.assertIn(BattleAction(ActionType.MOVE, move_id="earthquake"), legal.actions)
        self.assertIn(BattleAction(ActionType.SWITCH, switch_target_id="greattusk"), legal.actions)

    def test_team_export_does_not_reveal_opponent_set_to_policy_state(self) -> None:
        parsed = self._parsed()
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._artifacts())
        partial = parsed.partial_examples[0]
        legal = RecoveredLegalActionGenerator().generate(
            state=partial.observed_state,
            actor_side="p1",
            actor_team=resolution.player_1_team,
        )

        built = PolicyTrainingExampleBuilder().build(
            snapshot=parsed.snapshots[0],
            actor_team=resolution.player_1_team,
            legal_actions=legal,
            actual_action=partial.actual_action,
        )

        self.assertEqual(built.actual_action, BattleAction(ActionType.MOVE, move_id="earthquake"))
        self.assertEqual(built.observed_state.opponent.active.set_data.moves, ())
        self.assertIn(BattleAction(ActionType.MOVE, move_id="earthquake"), built.legal_actions)

    def test_statistical_moveset_cannot_create_training_example(self) -> None:
        parsed = self._parsed()
        hypothetical_team = self._hypothesized_team("p1")

        legal = RecoveredLegalActionGenerator().generate(
            state=parsed.partial_examples[0].observed_state,
            actor_side="p1",
            actor_team=hypothetical_team,
        )

        self.assertEqual(legal.quality, LegalActionQuality.UNAVAILABLE)
        self.assertIn("hypothesized_moveset_not_allowed", legal.missing_constraints)

    def test_information_revealed_later_is_not_visible_earlier(self) -> None:
        parsed = self._parsed()
        p1 = next(side for side in parsed.snapshots[0].state.sides if side.side == "p1")
        garchomp = next(pokemon for pokemon in p1.pokemon if pokemon.species_id == "garchomp")

        self.assertEqual(garchomp.revealed_moves, frozenset())

    def test_actual_action_must_exist_in_legal_actions(self) -> None:
        parsed = self._parsed()
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._artifacts())
        bad_legal = replace(
            RecoveredLegalActionGenerator().generate(
                state=parsed.partial_examples[0].observed_state,
                actor_side="p1",
                actor_team=resolution.player_1_team,
            ),
            actions=(BattleAction(ActionType.MOVE, move_id="stealthrock"),),
        )

        built = PolicyTrainingExampleBuilder().build(
            snapshot=parsed.snapshots[0],
            actor_team=resolution.player_1_team,
            legal_actions=bad_legal,
            actual_action=parsed.partial_examples[0].actual_action,
        )

        self.assertIsInstance(built, PartialPolicyExample)
        self.assertIn("actual_action_not_in_reconstructed_legal_actions", built.missing_information)

    def test_choice_lock_restricts_legal_moves_when_locked_move_is_observed(self) -> None:
        parsed = PublicReplayParser().parse(replay_id="choice", format_id="gen9ou", raw_log=self._choice_log())
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._choice_artifacts())
        turn_two = next(example for example in parsed.partial_examples if example.actual_action.turn == 2 and example.actual_action.side == "p2")

        legal = RecoveredLegalActionGenerator().generate(
            state=turn_two.observed_state,
            actor_side="p2",
            actor_team=resolution.player_2_team,
        )

        moves = tuple(action.move_id for action in legal.actions if action.move_id)
        self.assertEqual(moves, ("shadowball",))
        self.assertEqual(legal.quality, LegalActionQuality.RECONSTRUCTED_COMPLETE)

    def test_trapped_pokemon_cannot_switch(self) -> None:
        parsed = self._parsed()
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._artifacts())
        partial = parsed.partial_examples[0]
        p1_side = next(side for side in partial.observed_state.sides if side.side == "p1")
        trapped = tuple(replace(pokemon, trapped=True) if pokemon.active else pokemon for pokemon in p1_side.pokemon)
        trapped_state = replace(
            partial.observed_state,
            sides=tuple(replace(side, pokemon=trapped) if side.side == "p1" else side for side in partial.observed_state.sides),
        )

        legal = RecoveredLegalActionGenerator().generate(state=trapped_state, actor_side="p1", actor_team=resolution.player_1_team)

        self.assertFalse(any(action.switch_target_id for action in legal.actions))

    def test_forced_switch_only_contains_valid_switches(self) -> None:
        parsed = self._parsed()
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._artifacts())

        legal = RecoveredLegalActionGenerator().generate(
            state=parsed.partial_examples[0].observed_state,
            actor_side="p1",
            actor_team=resolution.player_1_team,
            forced_switch=True,
        )

        self.assertTrue(legal.actions)
        self.assertTrue(all(action.switch_target_id for action in legal.actions))

    def test_conflicting_team_export_is_rejected(self) -> None:
        parsed = PublicReplayParser().parse(
            replay_id="conflict",
            format_id="gen9ou",
            raw_log=self._simple_log(prefix="|-item|p1a: Garchomp|Choice Scarf\n"),
        )

        result = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, self._artifacts())

        self.assertTrue(result.conflicts)
        self.assertEqual(result.conflicts[0].field, "item")

    def test_reconstructed_actions_match_runner_actions(self) -> None:
        replay = ReplayLoader().load(ROOT_DIR / "runs" / "2026-07-20" / "policy-smoke-3")
        parsed = PublicReplayParser().parse(replay_id="policy-smoke-3", format_id="gen9ou", raw_log=self._runner_like_log())
        artifacts = ReplayArtifactBundle(
            player_1_team_export=(ROOT_DIR / "teams" / "team-a.txt").read_text(encoding="utf-8"),
            player_2_team_export=(ROOT_DIR / "teams" / "team-b.txt").read_text(encoding="utf-8"),
        )
        resolution = TeamEvidenceResolver().resolve(parsed, parsed.partial_examples, artifacts)
        first_runner_decision = next(record for record in replay.decisions if record.legal_actions and record.selected_action.move_id not in {"team", "unknown"})
        first_partial = next(example for example in parsed.partial_examples if example.actual_action.side == first_runner_decision.player_id)
        legal = RecoveredLegalActionGenerator().generate(
            state=first_partial.observed_state,
            actor_side=first_partial.actual_action.side,
            actor_team=resolution.player_1_team,
        )

        metrics = LegalActionDifferentialValidator().compare(
            authoritative=first_runner_decision.legal_actions,
            reconstructed=legal,
            actual_action=first_partial.actual_action.action,
        )

        self.assertEqual(metrics.actual_action_missing, 0)
        self.assertEqual(metrics.missing_actions, 0)

    def _parsed(self):
        return PublicReplayParser().parse(replay_id="simple", format_id="gen9ou", raw_log=self._simple_log())

    def _artifacts(self) -> ReplayArtifactBundle:
        return ReplayArtifactBundle(player_1_team_export=self._p1_export(), player_2_team_export=self._p2_export())

    def _choice_artifacts(self) -> ReplayArtifactBundle:
        return ReplayArtifactBundle(player_1_team_export=self._p1_export(), player_2_team_export=self._p2_export(choice=True))

    def _simple_log(self, prefix: str = "") -> str:
        return "\n".join(
            (
                "|poke|p1|Garchomp, M|",
                "|poke|p1|Great Tusk|",
                "|poke|p2|Dragapult, F|",
                "|switch|p1a: Garchomp|Garchomp, M|100/100",
                "|switch|p2a: Dragapult|Dragapult, F|100/100",
                prefix.rstrip(),
                "|turn|1",
                "|move|p1a: Garchomp|Earthquake|p2a: Dragapult",
                "|move|p2a: Dragapult|Shadow Ball|p1a: Garchomp",
            )
        )

    def _choice_log(self) -> str:
        return "\n".join(
            (
                self._simple_log(),
                "|turn|2",
                "|move|p2a: Dragapult|Shadow Ball|p1a: Garchomp",
            )
        )

    def _runner_like_log(self) -> str:
        return "\n".join(
            (
                "|poke|p1|Garchomp, M|",
                "|poke|p1|Great Tusk|",
                "|poke|p1|Kingambit, F|",
                "|poke|p1|Dragapult, F|",
                "|poke|p1|Rotom-Wash|",
                "|poke|p1|Clefable, M|",
                "|poke|p2|Dragapult, F|",
                "|switch|p1a: Garchomp|Garchomp, M|100/100",
                "|switch|p2a: Dragapult|Dragapult, F|100/100",
                "|turn|1",
                "|move|p1a: Garchomp|Earthquake|p2a: Dragapult",
            )
        )

    def _p1_export(self) -> str:
        return """
Garchomp @ Rocky Helmet
Ability: Rough Skin
- Stealth Rock
- Earthquake
- Dragon Tail
- Spikes

Great Tusk @ Heavy-Duty Boots
Ability: Protosynthesis
- Headlong Rush
- Rapid Spin
- Knock Off
- Ice Spinner
"""

    def _p2_export(self, choice: bool = False) -> str:
        item = "Choice Specs" if choice else "Leftovers"
        return f"""
Dragapult @ {item}
Ability: Infiltrator
- Draco Meteor
- Shadow Ball
- U-turn
- Flamethrower
"""

    def _hypothesized_team(self, side: str) -> ResolvedTeam:
        pokemon = PokemonSet("garchomp", None, None, None, 100, None, None, (), EVSpread())
        resolved = ResolvedPokemon(
            set_data=pokemon,
            species=EvidenceValue("garchomp", EvidenceSource.STATISTICAL_INFERENCE, EvidenceConfidence.INFERRED, None),
            moves=EvidenceValue(HypothesizedMoveSet((WeightedMoveSet(("earthquake",), 1.0),)), EvidenceSource.STATISTICAL_INFERENCE, EvidenceConfidence.INFERRED, None),
            item=EvidenceValue(None, EvidenceSource.STATISTICAL_INFERENCE, EvidenceConfidence.INFERRED, None),
            ability=EvidenceValue(None, EvidenceSource.STATISTICAL_INFERENCE, EvidenceConfidence.INFERRED, None),
            tera_type=EvidenceValue(None, EvidenceSource.STATISTICAL_INFERENCE, EvidenceConfidence.INFERRED, None),
        )
        return ResolvedTeam(side=side, team=Team("gen9ou", (pokemon,)), members=(resolved,), source=EvidenceSource.STATISTICAL_INFERENCE)


if __name__ == "__main__":
    unittest.main()
