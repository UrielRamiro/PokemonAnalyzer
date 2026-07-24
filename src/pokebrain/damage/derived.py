from __future__ import annotations


def calculate_ohko_chance(damage_rolls: tuple[int, ...], current_hp: int) -> float:
    if not damage_rolls:
        return 0.0
    ko_rolls = sum(damage >= current_hp for damage in damage_rolls)
    return ko_rolls / len(damage_rolls)


def classify_damage(minimum_percent: float, maximum_percent: float) -> str:
    if minimum_percent >= 100:
        return "guaranteed_ohko"
    if maximum_percent >= 100:
        return "possible_ohko"
    if minimum_percent >= 50:
        return "guaranteed_2hko"
    if maximum_percent >= 50:
        return "possible_2hko"
    return "three_hit_ko_or_more"

