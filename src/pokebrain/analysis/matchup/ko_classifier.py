from __future__ import annotations

import math

from pokebrain.analysis.matchup.models import KoRange, MoveMatchupResult


def calculate_expected_damage(
    damage_rolls: tuple[int, ...],
    accuracy: int | None,
) -> float:
    if not damage_rolls:
        return 0.0
    average_damage = sum(damage_rolls) / len(damage_rolls)
    hit_probability = 1.0 if accuracy is None else accuracy / 100
    return average_damage * hit_probability


def calculate_two_hko_chance(
    damage_rolls: tuple[int, ...],
    defender_hp: int,
) -> float | None:
    if not damage_rolls:
        return None
    ko_rolls = 0
    total = len(damage_rolls) * len(damage_rolls)
    for first in damage_rolls:
        for second in damage_rolls:
            if first + second >= defender_hp:
                ko_rolls += 1
    return ko_rolls / total


def classify_move_damage(
    minimum_percent: float,
    maximum_percent: float,
    is_status_move: bool,
    is_immune: bool,
) -> str:
    if is_status_move:
        return "status_move"
    if is_immune:
        return "immune"
    if minimum_percent >= 100:
        return "guaranteed_ohko"
    if maximum_percent >= 100:
        return "possible_ohko"
    if minimum_percent >= 50:
        return "guaranteed_2hko"
    if maximum_percent >= 50:
        return "possible_2hko"
    if minimum_percent >= 100 / 3:
        return "guaranteed_3hko"
    return "low_damage"


def move_score(result: MoveMatchupResult) -> tuple:
    return (
        result.ohko_chance,
        result.minimum_percent >= 100,
        result.maximum_percent >= 100,
        result.minimum_percent >= 50,
        result.expected_damage_percent,
        result.accuracy or 100,
    )


def calculate_ko_range(
    minimum_damage: int,
    maximum_damage: int,
    defender_hp: int,
) -> KoRange:
    optimistic = math.ceil(defender_hp / maximum_damage) if maximum_damage > 0 else None
    guaranteed = math.ceil(defender_hp / minimum_damage) if minimum_damage > 0 else None
    return KoRange(optimistic_turns=optimistic, guaranteed_turns=guaranteed)

