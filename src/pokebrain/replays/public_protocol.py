from __future__ import annotations

from pokebrain.replays.public_events import (
    AbilityRevealed,
    BattleEnded,
    BoostChanged,
    HpChanged,
    ItemConsumed,
    ItemRevealed,
    MoveUsed,
    PokemonFainted,
    PokemonPreviewed,
    PokemonSwitched,
    ReplayEvent,
    ReplayEventMetadata,
    SideConditionEnded,
    SideConditionStarted,
    StatusApplied,
    StatusRemoved,
    TeraUsed,
    TerrainChanged,
    TurnStarted,
    UnsupportedReplayEvent,
    WeatherChanged,
)
from pokebrain.utils import to_id


class ReplayProtocolParser:
    def parse(self, raw_log: str) -> tuple[ReplayEvent, ...]:
        events: list[ReplayEvent] = []
        current_turn: int | None = None
        for line_number, raw_line in enumerate(raw_log.splitlines(), start=1):
            if not raw_line.startswith("|"):
                continue
            parts = raw_line.split("|")
            command = parts[1] if len(parts) > 1 else ""
            metadata = ReplayEventMetadata(line_number=line_number, raw_line=raw_line, turn_number=current_turn)
            event = self._parse_line(parts, command, metadata)
            if isinstance(event, TurnStarted):
                current_turn = event.turn
                event = TurnStarted(event.turn, ReplayEventMetadata(line_number, raw_line, current_turn))
            if event is not None:
                events.append(event)
        return tuple(events)

    def _parse_line(
        self,
        parts: list[str],
        command: str,
        metadata: ReplayEventMetadata,
    ) -> ReplayEvent | None:
        try:
            if command in {"", "t:", "start", "rule", "gen", "tier", "gametype", "teamsize", "player", "clearpoke", "teampreview", "split"}:
                return None
            if command == "turn":
                return TurnStarted(int(parts[2]), metadata)
            if command == "poke":
                return PokemonPreviewed(side=parts[2], details=parts[3], metadata=metadata)
            if command in {"switch", "drag"}:
                return PokemonSwitched(
                    side=_side_from_ref(parts[2]),
                    pokemon_ref=parts[2],
                    details=parts[3],
                    hp_text=parts[4] if len(parts) > 4 else "",
                    metadata=metadata,
                )
            if command == "move":
                return MoveUsed(
                    side=_side_from_ref(parts[2]),
                    pokemon_ref=parts[2],
                    move_id=to_id(parts[3]),
                    target_ref=parts[4] if len(parts) > 4 else None,
                    metadata=metadata,
                )
            if command in {"-damage", "-heal"}:
                return HpChanged(
                    pokemon_ref=parts[2],
                    hp_text=parts[3],
                    cause=_extract_tag(parts[4:], "[from]"),
                    metadata=metadata,
                )
            if command == "faint":
                return PokemonFainted(pokemon_ref=parts[2], metadata=metadata)
            if command == "-status":
                return StatusApplied(pokemon_ref=parts[2], status=to_id(parts[3]), metadata=metadata)
            if command == "-curestatus":
                return StatusRemoved(pokemon_ref=parts[2], status=to_id(parts[3]), metadata=metadata)
            if command == "-boost":
                return BoostChanged(pokemon_ref=parts[2], stat=_stat_name(parts[3]), amount=int(parts[4]), metadata=metadata)
            if command == "-unboost":
                return BoostChanged(pokemon_ref=parts[2], stat=_stat_name(parts[3]), amount=-int(parts[4]), metadata=metadata)
            if command == "-ability":
                return AbilityRevealed(pokemon_ref=parts[2], ability_id=to_id(parts[3]), metadata=metadata)
            if command == "-item":
                return ItemRevealed(pokemon_ref=parts[2], item_id=to_id(parts[3]), metadata=metadata)
            if command == "-enditem":
                return ItemConsumed(pokemon_ref=parts[2], item_id=to_id(parts[3]), metadata=metadata)
            if command == "-weather":
                return WeatherChanged(weather=None if len(parts) < 3 or parts[2] in {"none", ""} else to_id(parts[2]), metadata=metadata)
            if command in {"-fieldstart", "-fieldend"} and len(parts) > 2 and "terrain" in parts[2].lower():
                return TerrainChanged(terrain=None if command == "-fieldend" else to_id(parts[2]), metadata=metadata)
            if command == "-sidestart":
                return SideConditionStarted(side=_side_from_ref(parts[2]), condition=to_id(parts[3]), metadata=metadata)
            if command == "-sideend":
                return SideConditionEnded(side=_side_from_ref(parts[2]), condition=to_id(parts[3]), metadata=metadata)
            if command == "-terastallize":
                return TeraUsed(pokemon_ref=parts[2], tera_type=parts[3], metadata=metadata)
            if command == "win":
                return BattleEnded(winner=parts[2] if len(parts) > 2 else None, metadata=metadata)
            if command == "tie":
                return BattleEnded(winner=None, metadata=metadata)
        except (IndexError, ValueError):
            return UnsupportedReplayEvent(raw_line=metadata.raw_line, command=command, metadata=metadata)
        return UnsupportedReplayEvent(raw_line=metadata.raw_line, command=command, metadata=metadata)


def _side_from_ref(ref: str) -> str:
    return ref.split(":", 1)[0][:2]


def _extract_tag(parts: list[str], tag: str) -> str | None:
    for index, part in enumerate(parts):
        if part == tag and index + 1 < len(parts):
            return parts[index + 1]
        if part.startswith(f"{tag} "):
            return part.removeprefix(f"{tag} ")
    return None


def _stat_name(stat: str) -> str:
    return {
        "atk": "attack",
        "def": "defense",
        "spa": "special_attack",
        "spd": "special_defense",
        "spe": "speed",
    }.get(stat, stat)
