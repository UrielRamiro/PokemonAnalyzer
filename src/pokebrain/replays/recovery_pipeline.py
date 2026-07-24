from __future__ import annotations

from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.replays.legal_recovery import RecoveredLegalActionGenerator
from pokebrain.replays.public_models import ParsedPublicReplay, PartialPolicyExample
from pokebrain.replays.recovery_models import DecisionKnowledge, EnrichedPolicyExample, ReplayArtifactBundle
from pokebrain.replays.team_recovery import TeamEvidenceResolver
from pokebrain.replays.training_builder import PolicyTrainingExampleBuilder


class TeamInformationRecoveryPipeline:
    def __init__(
        self,
        resolver: TeamEvidenceResolver | None = None,
        legal_generator: RecoveredLegalActionGenerator | None = None,
        example_builder: PolicyTrainingExampleBuilder | None = None,
    ) -> None:
        self.resolver = resolver or TeamEvidenceResolver()
        self.legal_generator = legal_generator or RecoveredLegalActionGenerator()
        self.example_builder = example_builder or PolicyTrainingExampleBuilder()

    def enrich(
        self,
        replay: ParsedPublicReplay,
        artifacts: ReplayArtifactBundle,
    ) -> tuple[EnrichedPolicyExample, ...]:
        resolution = self.resolver.resolve(replay, replay.partial_examples, artifacts)
        enriched = []
        for partial in replay.partial_examples:
            actor_team = resolution.player_1_team if partial.actual_action.side == "p1" else resolution.player_2_team
            legal_actions = self.legal_generator.generate(
                state=partial.observed_state,
                actor_side=partial.actual_action.side,
                actor_team=actor_team,
            )
            decision_knowledge = self.resolver.public_knowledge(partial.actual_action.side, partial.observed_state)
            opponent_side = "p1" if partial.actual_action.side == "p2" else "p2"
            opponent_knowledge = self.resolver.public_knowledge(opponent_side, partial.observed_state)
            snapshot = next(snapshot for snapshot in replay.snapshots if snapshot.turn == partial.observed_state.turn and snapshot.phase == "turn_start")
            built = self.example_builder.build(
                snapshot=snapshot,
                actor_team=actor_team,
                legal_actions=legal_actions,
                actual_action=partial.actual_action,
            ) if actor_team is not None else partial
            enriched.append(
                EnrichedPolicyExample(
                    snapshot=snapshot,
                    actual_action=partial.actual_action,
                    decision_knowledge=DecisionKnowledge(
                        actor_authoritative_team=actor_team,
                        actor_public_knowledge=decision_knowledge,
                        opponent_public_knowledge=opponent_knowledge,
                    ),
                    legal_actions=legal_actions,
                    partial_example=built if isinstance(built, PartialPolicyExample) else None,
                )
            )
        return tuple(enriched)

    def build_training_examples(
        self,
        replay: ParsedPublicReplay,
        artifacts: ReplayArtifactBundle,
    ) -> tuple[PolicyTrainingExample, ...]:
        examples: list[PolicyTrainingExample] = []
        resolution = self.resolver.resolve(replay, replay.partial_examples, artifacts)
        for partial in replay.partial_examples:
            actor_team = resolution.player_1_team if partial.actual_action.side == "p1" else resolution.player_2_team
            if actor_team is None:
                continue
            legal_actions = self.legal_generator.generate(
                state=partial.observed_state,
                actor_side=partial.actual_action.side,
                actor_team=actor_team,
            )
            snapshot = next(snapshot for snapshot in replay.snapshots if snapshot.turn == partial.observed_state.turn and snapshot.phase == "turn_start")
            built = self.example_builder.build(
                snapshot=snapshot,
                actor_team=actor_team,
                legal_actions=legal_actions,
                actual_action=partial.actual_action,
            )
            if isinstance(built, PolicyTrainingExample):
                examples.append(built)
        return tuple(examples)
