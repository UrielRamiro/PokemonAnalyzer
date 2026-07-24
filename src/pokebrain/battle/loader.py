from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokebrain.battle.models import ActivePokemonState, BattleSideState, BattleState
from pokebrain.team.models import EVSpread, IVSpread, PokemonSet
from pokebrain.utils import to_id


def load_battle_state(path: Path) -> BattleState:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return battle_state_from_dict(data)


def battle_state_from_dict(data: dict[str, Any]) -> BattleState:
    return BattleState(
        generation=int(data["generation"]),
        format_id=str(data["format_id"]),
        turn=int(data.get("turn", 1)),
        player=_side_from_dict(data["player"]),
        opponent=_side_from_dict(data["opponent"]),
        weather=_optional_id(data.get("weather")),
        terrain=_optional_id(data.get("terrain")),
        trick_room_turns=int(data.get("trick_room_turns", 0)),
    )


def _side_from_dict(data: dict[str, Any]) -> BattleSideState:
    team = tuple(_pokemon_set_from_dict(member) for member in data["team"])
    active_data = data.get("active")
    if active_data is None:
        active_data = data.get("active_state")
    if active_data is None:
        active_set = team[0]
        active_data = {"species": active_set.species_id}
    active_set = _active_set(active_data, team)

    return BattleSideState(
        active=ActivePokemonState(
            set_data=active_set,
            current_hp=int(active_data.get("current_hp", active_data.get("currentHp", 1))),
            status=_optional_id(active_data.get("status")),
            attack_stage=int(active_data.get("attack_stage", 0)),
            defense_stage=int(active_data.get("defense_stage", 0)),
            special_attack_stage=int(active_data.get("special_attack_stage", 0)),
            special_defense_stage=int(active_data.get("special_defense_stage", 0)),
            speed_stage=int(active_data.get("speed_stage", 0)),
            confused=bool(active_data.get("confused", False)),
            trapped=bool(active_data.get("trapped", False)),
        ),
        team=team,
        fainted_ids=tuple(to_id(value) for value in data.get("fainted_ids", ())),
        stealth_rock=bool(data.get("stealth_rock", False)),
        spikes_layers=int(data.get("spikes_layers", 0)),
        toxic_spikes_layers=int(data.get("toxic_spikes_layers", 0)),
        sticky_web=bool(data.get("sticky_web", False)),
    )


def _active_set(active_data: dict[str, Any], team: tuple[PokemonSet, ...]) -> PokemonSet:
    species_id = to_id(str(active_data["species"]))
    for member in team:
        if member.species_id == species_id:
            return member
    return _pokemon_set_from_dict(active_data)


def _pokemon_set_from_dict(data: dict[str, Any]) -> PokemonSet:
    evs = data.get("evs", {})
    ivs = data.get("ivs", {})
    return PokemonSet(
        species_id=to_id(str(data["species"])),
        nickname=data.get("nickname"),
        item_id=_optional_id(data.get("item")),
        ability_id=_optional_id(data.get("ability")),
        level=int(data.get("level", 100)),
        nature=data.get("nature"),
        tera_type=data.get("teraType") or data.get("tera_type"),
        moves=tuple(_optional_id(move) or "" for move in data.get("moves", ())),
        evs=EVSpread(
            hp=int(evs.get("hp", 0)),
            attack=int(evs.get("atk", evs.get("attack", 0))),
            defense=int(evs.get("def", evs.get("defense", 0))),
            special_attack=int(evs.get("spa", evs.get("special_attack", 0))),
            special_defense=int(evs.get("spd", evs.get("special_defense", 0))),
            speed=int(evs.get("spe", evs.get("speed", 0))),
        ),
        ivs=IVSpread(
            hp=int(ivs.get("hp", 31)),
            attack=int(ivs.get("atk", ivs.get("attack", 31))),
            defense=int(ivs.get("def", ivs.get("defense", 31))),
            special_attack=int(ivs.get("spa", ivs.get("special_attack", 31))),
            special_defense=int(ivs.get("spd", ivs.get("special_defense", 31))),
            speed=int(ivs.get("spe", ivs.get("speed", 31))),
        ),
    )


def _optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    return to_id(str(value))
