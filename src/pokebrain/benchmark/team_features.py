from __future__ import annotations

from pathlib import Path

from pokebrain.team.parser import TeamParser


RAIN_SETTERS = {"pelipper", "politoed"}
SUN_SETTERS = {"torkoal", "ninetales", "ninetalesalola"}
SNOW_SETTERS = {"ninetalesalola", "abomasnow", "slowkinggalar"}
STALL_HINTS = {"blissey", "chansey", "toxapex", "clodsire", "dondozo", "corviknight", "skarmory", "clefable"}
OFFENSE_HINTS = {"dragapult", "ironvaliant", "chienpao", "roaringmoon", "deoxysattack", "barraskewda"}
SETUP_MOVES = {"swordsdance", "dragondance", "nastyplot", "calmmind", "quiverdance", "shellsmash"}
HAZARD_MOVES = {"stealthrock", "spikes", "toxicspikes", "stickyweb"}


def species_ids_from_team_file(format_id: str, path: Path) -> tuple[str, ...]:
    team = TeamParser().parse(format_id, path.read_text(encoding="utf-8")).team
    if team is None:
        return ()
    return tuple(member.species_id for member in team.members)


def classify_team_archetype(format_id: str, path: Path) -> str:
    team = TeamParser().parse(format_id, path.read_text(encoding="utf-8")).team
    if team is None:
        return "unknown"
    species = {member.species_id for member in team.members}
    moves = {move for member in team.members for move in member.moves}
    setup_count = sum(1 for member in team.members if SETUP_MOVES.intersection(member.moves))
    hazard_count = len(HAZARD_MOVES.intersection(moves))

    if RAIN_SETTERS.intersection(species):
        return "rain"
    if SUN_SETTERS.intersection(species):
        return "sun"
    if SNOW_SETTERS.intersection(species):
        return "snow"
    if len(STALL_HINTS.intersection(species)) >= 3:
        return "stall"
    if setup_count >= 3 or len(OFFENSE_HINTS.intersection(species)) >= 3:
        return "hyper-offense"
    if hazard_count >= 2 and setup_count <= 1:
        return "balance"
    return "balance"


def text_tuple(values: tuple[str, ...]) -> str:
    return ",".join(values)


def tuple_from_text(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part for part in value.split(",") if part)
