from __future__ import annotations

from pokebrain.battle.models import ActionType
from pokebrain.replay.models import DecisionErrorType, DecisionRecord


HAZARD_REMOVAL_MOVES = {"rapidspin", "defog", "mortalspin", "tidyup"}
SETUP_MOVES = {"swordsdance", "dragondance", "nastyplot", "calmmind", "quiverdance", "shellsmash"}


def detect_error_types(record: DecisionRecord) -> tuple[DecisionErrorType, ...]:
    errors: list[DecisionErrorType] = []
    if detect_attacked_immunity(record):
        errors.append(DecisionErrorType.ATTACKED_IMMUNITY)
    if detect_missed_guaranteed_ko(record):
        errors.append(DecisionErrorType.MISSED_KO)
    if detect_failed_to_switch(record):
        errors.append(DecisionErrorType.FAILED_TO_SWITCH)
    if detect_bad_switch(record):
        errors.append(DecisionErrorType.BAD_SWITCH)
    if detect_failed_to_remove_hazards(record):
        errors.append(DecisionErrorType.FAILED_TO_REMOVE_HAZARDS)
    if detect_unsafe_setup(record):
        errors.append(DecisionErrorType.UNSAFE_SETUP)
    if not errors and _best_alternative_gap(record) >= 20:
        errors.append(DecisionErrorType.POOR_MOVE_SELECTION)
    return tuple(errors) or (DecisionErrorType.UNKNOWN,)


def detect_attacked_immunity(record: DecisionRecord) -> bool:
    if record.selected_action.action_type is not ActionType.MOVE:
        return False
    text = " ".join((*record.selected_evaluation.risks, *record.risks, *record.selected_evaluation.reasons)).lower()
    return "immune" in text or record.selected_evaluation.average_utility <= -50


def detect_missed_guaranteed_ko(record: DecisionRecord) -> bool:
    selected_text = " ".join(record.selected_evaluation.reasons).lower()
    if "guarantees a ko" in selected_text:
        return False
    return any("guarantees a ko" in " ".join(alternative.reasons).lower() for alternative in record.alternative_evaluations)


def detect_failed_to_switch(record: DecisionRecord) -> bool:
    if record.selected_action.action_type is ActionType.SWITCH:
        return False
    best_switch = max(
        (alternative.average_utility for alternative in record.alternative_evaluations if alternative.action.action_type is ActionType.SWITCH),
        default=None,
    )
    return best_switch is not None and best_switch - record.selected_evaluation.average_utility >= 30


def detect_bad_switch(record: DecisionRecord) -> bool:
    if record.selected_action.action_type is not ActionType.SWITCH:
        return False
    risk_text = " ".join((*record.selected_evaluation.risks, *record.risks)).lower()
    return "koed on entry" in risk_text or "more than 50%" in risk_text


def detect_failed_to_remove_hazards(record: DecisionRecord) -> bool:
    if record.selected_action.move_id in HAZARD_REMOVAL_MOVES:
        return False
    if not record.battle_state.player.stealth_rock:
        return False
    return any(
        alternative.action.move_id in HAZARD_REMOVAL_MOVES
        and alternative.average_utility - record.selected_evaluation.average_utility >= 15
        for alternative in record.alternative_evaluations
    )


def detect_unsafe_setup(record: DecisionRecord) -> bool:
    if record.selected_action.move_id not in SETUP_MOVES:
        return False
    risk_text = " ".join((*record.selected_evaluation.risks, *record.risks)).lower()
    return "ko" in risk_text or _best_alternative_gap(record) >= 20


def _best_alternative_gap(record: DecisionRecord) -> float:
    best = max((alternative.average_utility for alternative in record.alternative_evaluations), default=record.selected_evaluation.average_utility)
    return best - record.selected_evaluation.average_utility
