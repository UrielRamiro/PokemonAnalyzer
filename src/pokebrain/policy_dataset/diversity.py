from __future__ import annotations

from collections import Counter

from pokebrain.battle.models import ActionType
from pokebrain.policy_dataset.models import PolicyDatasetDiversityReport, PolicyDatasetRecord


class PolicyDatasetDiversityReporter:
    def report(self, records: tuple[PolicyDatasetRecord, ...]) -> PolicyDatasetDiversityReport:
        player_teams = {_team_id(tuple(member.species_id for member in record.example.observed_state.player.team)) for record in records}
        opponent_teams = {_team_id(tuple(member.species_id for member in record.example.observed_state.opponent.team)) for record in records}
        species_combinations = {
            _team_id(tuple(sorted(member.species_id for member in (*record.example.observed_state.player.team, *record.example.observed_state.opponent.team))))
            for record in records
        }
        species = {
            member.species_id
            for record in records
            for member in (*record.example.observed_state.player.team, *record.example.observed_state.opponent.team)
        }
        return PolicyDatasetDiversityReport(
            decisions=len(records),
            battles=len({record.metadata.replay_id for record in records}),
            unique_player_teams=len(player_teams),
            unique_opponent_teams=len(opponent_teams),
            unique_species=len(species),
            unique_species_combinations=len(species_combinations),
            by_turn_bucket=tuple(sorted(Counter(_turn_bucket(record.metadata.turn_number) for record in records).items())),
            by_legal_action_count=tuple(sorted(Counter(_legal_action_bucket(len(record.example.legal_actions)) for record in records).items())),
            by_action_type=tuple(sorted(Counter(_action_type(record) for record in records).items())),
            tera_available=sum(1 for record in records if _tera_available(record)),
            hazards_present=sum(1 for record in records if _hazards_present(record)),
            weather_present=sum(1 for record in records if record.example.observed_state.weather),
            terrain_present=sum(1 for record in records if record.example.observed_state.terrain),
            forced_switch_states=sum(1 for record in records if _forced_switch(record)),
            choice_lock_states=sum(1 for record in records if _choice_lock(record)),
            by_agent=(("unknown", len(records)),),
        )


def _team_id(species: tuple[str, ...]) -> str:
    return "|".join(sorted(species))


def _turn_bucket(turn: int) -> str:
    if turn <= 5:
        return "turns_1_5"
    if turn <= 10:
        return "turns_6_10"
    if turn <= 20:
        return "turns_11_20"
    return "turns_20_plus"


def _legal_action_bucket(count: int) -> str:
    if count <= 1:
        return "1"
    if count <= 4:
        return "2_4"
    if count <= 8:
        return "5_8"
    return "9_plus"


def _action_type(record: PolicyDatasetRecord) -> str:
    return "switch" if record.example.actual_action.action_type is ActionType.SWITCH else "attack"


def _tera_available(record: PolicyDatasetRecord) -> bool:
    return any(member.tera_type for member in (*record.example.observed_state.player.team, *record.example.observed_state.opponent.team))


def _hazards_present(record: PolicyDatasetRecord) -> bool:
    state = record.example.observed_state
    return any(
        (
            state.player.stealth_rock,
            state.opponent.stealth_rock,
            state.player.spikes_layers,
            state.opponent.spikes_layers,
            state.player.toxic_spikes_layers,
            state.opponent.toxic_spikes_layers,
            state.player.sticky_web,
            state.opponent.sticky_web,
        )
    )


def _forced_switch(record: PolicyDatasetRecord) -> bool:
    return bool(record.example.legal_actions) and all(action.action_type is ActionType.SWITCH for action in record.example.legal_actions)


def _choice_lock(record: PolicyDatasetRecord) -> bool:
    item_id = record.example.observed_state.opponent.active.set_data.item_id or ""
    return item_id in {"choiceband", "choicescarf", "choicespecs"}
