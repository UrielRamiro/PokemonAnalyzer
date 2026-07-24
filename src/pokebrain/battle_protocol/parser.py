from __future__ import annotations

from pokebrain.battle_protocol.events import (
    BattleEvent,
    DamageEvent,
    FaintEvent,
    HealEvent,
    AbilityEvent,
    ItemEvent,
    MoveEvent,
    SideEndEvent,
    SideStartEvent,
    SwitchEvent,
    TerastallizeEvent,
    TurnEvent,
    UnknownBattleEvent,
    WeatherEvent,
    WinEvent,
)


def parse_protocol_line(line: str) -> BattleEvent | None:
    if not line.startswith("|"):
        return None
    parts = line.split("|")
    message_type = parts[1] if len(parts) > 1 else ""

    if message_type == "turn":
        return TurnEvent(turn=int(parts[2]))
    if message_type in {"switch", "drag"}:
        return SwitchEvent(
            pokemon_identifier=parts[2],
            details=parts[3],
            condition=parts[4],
        )
    if message_type == "move":
        return MoveEvent(
            pokemon_identifier=parts[2],
            move_id=_to_id(parts[3]),
            target_identifier=parts[4] if len(parts) > 4 else None,
        )
    if message_type == "-damage":
        return DamageEvent(
            pokemon_identifier=parts[2],
            condition=parts[3],
            source=_extract_tag(parts[4:], "[from]"),
        )
    if message_type == "-heal":
        return HealEvent(
            pokemon_identifier=parts[2],
            condition=parts[3],
            source=_extract_tag(parts[4:], "[from]"),
        )
    if message_type == "-item":
        return ItemEvent(pokemon_identifier=parts[2], item_id=_to_id(parts[3]))
    if message_type == "-ability":
        return AbilityEvent(pokemon_identifier=parts[2], ability_id=_to_id(parts[3]))
    if message_type == "-terastallize":
        return TerastallizeEvent(pokemon_identifier=parts[2], tera_type=parts[3])
    if message_type == "faint":
        return FaintEvent(pokemon_identifier=parts[2])
    if message_type == "-weather":
        return WeatherEvent(weather=None if len(parts) < 3 or parts[2] == "none" else parts[2])
    if message_type == "-sidestart":
        return SideStartEvent(side_identifier=parts[2], effect=parts[3])
    if message_type == "-sideend":
        return SideEndEvent(side_identifier=parts[2], effect=parts[3])
    if message_type == "win":
        return WinEvent(winner=parts[2] if len(parts) > 2 else None)
    if message_type == "tie":
        return WinEvent(winner=None)

    return UnknownBattleEvent(message_type=message_type, raw_line=line)


def _extract_tag(parts: list[str], tag: str) -> str | None:
    for index, part in enumerate(parts):
        if part == tag and index + 1 < len(parts):
            return parts[index + 1]
        if part.startswith(f"{tag} "):
            return part.removeprefix(f"{tag} ")
    return None


def _to_id(value: str) -> str:
    from pokebrain.utils import to_id

    return to_id(value)
