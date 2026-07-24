from __future__ import annotations

from pokebrain.utils import to_id


def player_id_from_identifier(identifier: str) -> str | None:
    if identifier.startswith("p1"):
        return "p1"
    if identifier.startswith("p2"):
        return "p2"
    return None


def species_id_from_identifier(identifier: str) -> str:
    name = identifier.split(":", 1)[-1]
    return to_id(name)
