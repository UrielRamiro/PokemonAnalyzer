from __future__ import annotations

from pokebrain.battle.models import ActionType, BattleState
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.policy_dataset.models import FeatureSchema, FeatureVector


FEATURE_SCHEMA = FeatureSchema(
    version="policy-features-v1",
    feature_names=(
        "turn",
        "player_hp_fraction",
        "opponent_hp_fraction",
        "player_team_size",
        "opponent_team_size",
        "player_revealed_move_count",
        "opponent_revealed_move_count",
        "player_item_known",
        "opponent_item_known",
        "legal_action_count",
        "legal_move_count",
        "legal_switch_count",
        "actual_is_move",
        "actual_is_switch",
        "weather_present",
        "terrain_present",
    ),
)


class FeatureExtractor:
    schema = FEATURE_SCHEMA

    def transform(self, example: PolicyTrainingExample) -> FeatureVector:
        state = example.observed_state
        legal_moves = sum(1 for action in example.legal_actions if action.action_type is ActionType.MOVE)
        legal_switches = sum(1 for action in example.legal_actions if action.action_type is ActionType.SWITCH)
        values = (
            float(state.turn),
            _hp_fraction(state, "player"),
            _hp_fraction(state, "opponent"),
            float(len(state.player.team)),
            float(len(state.opponent.team)),
            float(len(state.player.active.set_data.moves)),
            float(len(state.opponent.active.set_data.moves)),
            1.0 if state.player.active.set_data.item_id else 0.0,
            1.0 if state.opponent.active.set_data.item_id else 0.0,
            float(len(example.legal_actions)),
            float(legal_moves),
            float(legal_switches),
            1.0 if example.actual_action.action_type is ActionType.MOVE else 0.0,
            1.0 if example.actual_action.action_type is ActionType.SWITCH else 0.0,
            1.0 if state.weather else 0.0,
            1.0 if state.terrain else 0.0,
        )
        return FeatureVector(schema_version=self.schema.version, values=values)


def _hp_fraction(state: BattleState, side: str) -> float:
    active = state.player.active if side == "player" else state.opponent.active
    return max(0.0, min(1.0, active.current_hp / 100))
