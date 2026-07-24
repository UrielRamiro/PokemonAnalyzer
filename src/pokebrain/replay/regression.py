from __future__ import annotations

import json
from pathlib import Path

from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.replay.models import BattleReview, DecisionErrorType, RegressionCase


def write_regression_cases(review: BattleReview, output_dir: Path, limit: int = 5) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for decision in review.critical_decisions[:limit]:
        error = next((item for item in decision.error_types if item is not DecisionErrorType.UNKNOWN), DecisionErrorType.UNKNOWN)
        case = RegressionCase(
            case_id=f"{error.value}-{review.battle_id}-turn-{decision.record.turn}",
            source_battle_id=review.battle_id,
            source_turn=decision.record.turn,
            state=decision.record.battle_state,
            acceptable_actions=_best_actions(decision.record),
            forbidden_actions=(decision.record.selected_action,),
            error_type=error,
        )
        path = output_dir / f"{case.case_id}.json"
        path.write_text(json.dumps(_case_to_json(case), indent=2), encoding="utf-8")
        paths.append(path)
    return tuple(paths)


def _best_actions(record) -> tuple[BattleAction, ...]:
    if not record.alternative_evaluations:
        return ()
    best = max(alternative.average_utility for alternative in record.alternative_evaluations)
    return tuple(alternative.action for alternative in record.alternative_evaluations if alternative.average_utility == best)


def _case_to_json(case: RegressionCase) -> dict:
    return {
        "case_id": case.case_id,
        "source_battle_id": case.source_battle_id,
        "source_turn": case.source_turn,
        "error_type": case.error_type.value,
        "state": _state_to_json(case.state),
        "acceptable_actions": [_action_to_json(action) for action in case.acceptable_actions],
        "forbidden_actions": [_action_to_json(action) for action in case.forbidden_actions],
    }


def _action_to_json(action: BattleAction) -> dict:
    if action.action_type is ActionType.MOVE:
        return {"type": "move", "move_id": action.move_id}
    return {"type": "switch", "switch_target_id": action.switch_target_id}


def _state_to_json(state) -> dict:
    return {
        "generation": state.generation,
        "format_id": state.format_id,
        "turn": state.turn,
        "player": _side_to_json(state.player),
        "opponent": _side_to_json(state.opponent),
        "weather": state.weather,
        "terrain": state.terrain,
    }


def _side_to_json(side) -> dict:
    return {
        "active": {
            "species": side.active.set_data.species_id,
            "current_hp": side.active.current_hp,
        },
        "team": [_set_to_json(member) for member in side.team],
        "fainted_ids": side.fainted_ids,
        "stealth_rock": side.stealth_rock,
    }


def _set_to_json(pokemon_set) -> dict:
    return {
        "species": pokemon_set.species_id,
        "item": pokemon_set.item_id,
        "ability": pokemon_set.ability_id,
        "level": pokemon_set.level,
        "nature": pokemon_set.nature,
        "tera_type": pokemon_set.tera_type,
        "moves": pokemon_set.moves,
        "evs": {
            "hp": pokemon_set.evs.hp,
            "atk": pokemon_set.evs.attack,
            "def": pokemon_set.evs.defense,
            "spa": pokemon_set.evs.special_attack,
            "spd": pokemon_set.evs.special_defense,
            "spe": pokemon_set.evs.speed,
        },
        "ivs": {
            "hp": pokemon_set.ivs.hp,
            "atk": pokemon_set.ivs.attack,
            "def": pokemon_set.ivs.defense,
            "spa": pokemon_set.ivs.special_attack,
            "spd": pokemon_set.ivs.special_defense,
            "spe": pokemon_set.ivs.speed,
        },
    }
