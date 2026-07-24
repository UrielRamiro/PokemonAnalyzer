from __future__ import annotations

from pokebrain.belief.models import MAX_UNREVEALED_PROBABILITY, UNKNOWN_VALUE, WeightedValue


def normalize[T](values: tuple[WeightedValue[T], ...]) -> tuple[WeightedValue[T], ...]:
    total = sum(max(0.0, value.probability) for value in values)
    if total <= 0:
        return ()
    return tuple(
        WeightedValue(value=item.value, probability=max(0.0, item.probability) / total)
        for item in values
        if item.probability > 0
    )


def collapse_to(value: str) -> tuple[WeightedValue[str], ...]:
    return (WeightedValue(value, 1.0),)


def remove_value(values: tuple[WeightedValue[str], ...], value: str) -> tuple[WeightedValue[str], ...]:
    reduced = tuple(item for item in values if item.value != value)
    normalized = normalize(reduced)
    if normalized:
        return normalized
    return (WeightedValue(UNKNOWN_VALUE, 1.0),)


def ensure_uncertainty_floor(values: tuple[WeightedValue[str], ...]) -> tuple[WeightedValue[str], ...]:
    normalized = normalize(values)
    if not normalized:
        return (WeightedValue(UNKNOWN_VALUE, 1.0),)
    if len(normalized) == 1:
        only = normalized[0]
        if only.value == UNKNOWN_VALUE:
            return normalized
        return (
            WeightedValue(only.value, MAX_UNREVEALED_PROBABILITY),
            WeightedValue(UNKNOWN_VALUE, 1.0 - MAX_UNREVEALED_PROBABILITY),
        )
    top = normalized[0]
    if top.probability <= MAX_UNREVEALED_PROBABILITY:
        return normalized
    remainder_scale = (1.0 - MAX_UNREVEALED_PROBABILITY) / (1.0 - top.probability)
    return normalize(
        (WeightedValue(top.value, MAX_UNREVEALED_PROBABILITY),)
        + tuple(WeightedValue(item.value, item.probability * remainder_scale) for item in normalized[1:])
    )
