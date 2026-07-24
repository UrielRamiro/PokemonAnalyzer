from __future__ import annotations

from pokebrain.team.models import EVSpread, IVSpread


def is_champions_format(format_id: str | None) -> bool:
    return "champions" in (format_id or "").lower()


def validate_spread_for_format(format_id: str, evs: EVSpread, ivs: IVSpread) -> tuple[str, ...]:
    if not is_champions_format(format_id):
        return ()
    errors: list[str] = []
    values = _spread_values(evs)
    over_cap = tuple(name for name, value in values.items() if value > 32)
    if over_cap:
        errors.append(f"Champions stat points must be at most 32 per stat: {', '.join(over_cap)}.")
    total = sum(values.values())
    if total > 66:
        errors.append(f"Champions stat points total must be at most 66, got {total}.")
    if ivs != IVSpread():
        errors.append("Champions fixes IVs at 31 in every stat; custom IVs are not legal.")
    return tuple(errors)


def stat_investment_for_formula(ev: int, format_id: str | None) -> int:
    if is_champions_format(format_id):
        return ev
    return ev // 4


def effective_ivs_for_format(ivs: IVSpread, format_id: str | None) -> IVSpread:
    if is_champions_format(format_id):
        return IVSpread()
    return ivs


def evs_for_damage_calculator(evs: EVSpread, format_id: str | None) -> dict[str, int]:
    multiplier = 4 if is_champions_format(format_id) else 1
    return {
        "hp": evs.hp * multiplier,
        "atk": evs.attack * multiplier,
        "def": evs.defense * multiplier,
        "spa": evs.special_attack * multiplier,
        "spd": evs.special_defense * multiplier,
        "spe": evs.speed * multiplier,
    }


def _spread_values(evs: EVSpread) -> dict[str, int]:
    return {
        "HP": evs.hp,
        "Atk": evs.attack,
        "Def": evs.defense,
        "SpA": evs.special_attack,
        "SpD": evs.special_defense,
        "Spe": evs.speed,
    }
