from __future__ import annotations

import re
from dataclasses import dataclass

from pokebrain.team.models import EVSpread, IVSpread, PokemonSet, Team
from pokebrain.team.stat_system import validate_spread_for_format
from pokebrain.utils import to_id


EV_MAP = {
    "HP": "hp",
    "Atk": "attack",
    "Def": "defense",
    "SpA": "special_attack",
    "SpD": "special_defense",
    "Spe": "speed",
}


@dataclass(frozen=True, slots=True)
class ParsedTeamResult:
    team: Team | None
    parse_errors: tuple[str, ...]


class TeamParser:
    def parse(self, format_id: str, team_text: str) -> ParsedTeamResult:
        errors: list[str] = []
        members: list[PokemonSet] = []
        blocks = [block.strip() for block in re.split(r"\n\s*\n", team_text.strip()) if block.strip()]

        for index, block in enumerate(blocks, start=1):
            try:
                members.append(self._parse_member(format_id, block))
            except ValueError as error:
                errors.append(f"Member {index}: {error}")

        team = Team(format_id=format_id, members=tuple(members)) if members else None
        return ParsedTeamResult(team=team, parse_errors=tuple(errors))

    def _parse_member(self, format_id: str, block: str) -> PokemonSet:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            raise ValueError("empty set.")

        nickname, species, item = self._parse_header(lines[0])
        ability_id: str | None = None
        level = 100
        nature: str | None = None
        tera_type: str | None = None
        evs = EVSpread()
        ivs = IVSpread()
        moves: list[str] = []

        for line in lines[1:]:
            if line.startswith("Ability:"):
                ability_id = to_id(line.split(":", 1)[1].strip())
            elif line.startswith("Level:"):
                level = int(line.split(":", 1)[1].strip())
            elif line.startswith("Tera Type:"):
                tera_type = line.split(":", 1)[1].strip()
            elif line.startswith("EVs:"):
                evs = self._parse_evs(line.split(":", 1)[1].strip())
            elif line.startswith("IVs:"):
                ivs = self._parse_ivs(line.split(":", 1)[1].strip())
            elif line.endswith("Nature"):
                nature = line.removesuffix("Nature").strip()
            elif line.startswith("-"):
                moves.append(to_id(line[1:].strip()))

        member = PokemonSet(
            species_id=to_id(species),
            nickname=nickname,
            item_id=to_id(item) if item else None,
            ability_id=ability_id,
            level=level,
            nature=nature,
            tera_type=tera_type,
            moves=tuple(moves),
            evs=evs,
            ivs=ivs,
        )
        errors = validate_spread_for_format(format_id, evs, ivs)
        if errors:
            raise ValueError(" ".join(errors))
        return member

    def _parse_header(self, line: str) -> tuple[str | None, str, str | None]:
        left, _, item = line.partition("@")
        item = item.strip() or None
        name = left.strip()

        match = re.match(r"^(?P<nickname>.+)\((?P<species>[^)]+)\)$", name)
        if match:
            return match.group("nickname").strip(), match.group("species").strip(), item

        return None, name, item

    def _parse_evs(self, text: str) -> EVSpread:
        values = {
            "hp": 0,
            "attack": 0,
            "defense": 0,
            "special_attack": 0,
            "special_defense": 0,
            "speed": 0,
        }
        for part in text.split("/"):
            amount_text, stat_name = part.strip().split(" ", 1)
            key = EV_MAP.get(stat_name.strip())
            if key:
                values[key] = int(amount_text)
        return EVSpread(**values)

    def _parse_ivs(self, text: str) -> IVSpread:
        values = {
            "hp": 31,
            "attack": 31,
            "defense": 31,
            "special_attack": 31,
            "special_defense": 31,
            "speed": 31,
        }
        for part in text.split("/"):
            amount_text, stat_name = part.strip().split(" ", 1)
            key = EV_MAP.get(stat_name.strip())
            if key:
                values[key] = int(amount_text)
        return IVSpread(**values)
