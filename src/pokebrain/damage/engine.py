from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Protocol

from pokebrain.damage.derived import calculate_ohko_chance, classify_damage
from pokebrain.damage.models import DamagePokemon, DamageRequest, DamageResult, FieldState
from pokebrain.team.models import PokemonSet


ROOT_DIR = Path(__file__).resolve().parents[3]


class DamageEngineError(RuntimeError):
    pass


class DamageEngine(Protocol):
    def calculate(self, request: DamageRequest) -> DamageResult:
        ...

    def calculate_many(self, requests: tuple[DamageRequest, ...]) -> tuple[DamageResult, ...]:
        ...


class ShowdownDamageEngine:
    def __init__(
        self,
        node_executable: str = "node",
        bridge_script: Path | str = ROOT_DIR / "scripts" / "showdown_bridge.js",
        root_dir: Path | str = ROOT_DIR,
    ) -> None:
        self.node_executable = node_executable
        self.bridge_script = Path(bridge_script)
        self.root_dir = Path(root_dir)

    def calculate(self, request: DamageRequest) -> DamageResult:
        payload = serialize_damage_request(request)
        process = subprocess.run(
            [self.node_executable, str(self.bridge_script), "calculate-damage"],
            cwd=self.root_dir,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if process.returncode != 0:
            raise DamageEngineError(
                process.stderr.strip()
                or process.stdout.strip()
                or "Damage calculator failed."
            )

        response = json.loads(process.stdout)
        if not response.get("ok"):
            raise DamageEngineError(response.get("error", "Damage calculator failed."))

        return deserialize_damage_result(response)

    def calculate_many(self, requests: tuple[DamageRequest, ...]) -> tuple[DamageResult, ...]:
        if not requests:
            return ()
        payload = {
            "requests": [
                {
                    "requestId": f"damage-{index}",
                    "calculation": serialize_damage_request(request),
                }
                for index, request in enumerate(requests)
            ]
        }
        process = subprocess.run(
            [self.node_executable, str(self.bridge_script), "calculate-damage-batch"],
            cwd=self.root_dir,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if process.returncode != 0:
            raise DamageEngineError(
                process.stderr.strip()
                or process.stdout.strip()
                or "Damage calculator batch failed."
            )

        response = json.loads(process.stdout)
        if not response.get("ok"):
            raise DamageEngineError(response.get("error", "Damage calculator batch failed."))

        ordered = sorted(response["results"], key=lambda item: int(str(item["requestId"]).split("-")[-1]))
        return tuple(deserialize_damage_result(item["result"]) for item in ordered)


def serialize_damage_request(request: DamageRequest) -> dict[str, Any]:
    return {
        "generation": request.generation,
        "attacker": serialize_damage_pokemon(request.attacker, request.format_id),
        "defender": serialize_damage_pokemon(request.defender, request.format_id),
        "move": request.move_id,
        "field": serialize_field_state(request.field),
    }


def serialize_damage_pokemon(pokemon: DamagePokemon | PokemonSet, format_id: str | None = None) -> dict[str, Any]:
    damage_pokemon = (
        DamagePokemon.from_team_set(pokemon, format_id)
        if isinstance(pokemon, PokemonSet)
        else pokemon
    )
    return {
        "species": damage_pokemon.species,
        "level": damage_pokemon.level,
        "ability": damage_pokemon.ability,
        "item": damage_pokemon.item,
        "nature": damage_pokemon.nature,
        "evs": damage_pokemon.evs,
        "ivs": damage_pokemon.ivs,
        "boosts": damage_pokemon.boosts,
        "status": damage_pokemon.status,
        "teraType": damage_pokemon.tera_type,
        "currentHp": damage_pokemon.current_hp,
    }


def serialize_field_state(field: FieldState) -> dict[str, Any]:
    return {
        "weather": field.weather,
        "terrain": field.terrain,
        "reflect": field.reflect,
        "lightScreen": field.light_screen,
        "auroraVeil": field.aurora_veil,
        "attackerTailwind": field.attacker_tailwind,
        "defenderTailwind": field.defender_tailwind,
        "helpingHand": field.helping_hand,
        "friendGuard": field.friend_guard,
        "isDoubles": field.is_doubles,
    }


def deserialize_damage_result(payload: dict[str, Any]) -> DamageResult:
    rolls = tuple(int(value) for value in payload["damageRolls"])
    defender_hp = int(payload["defenderMaxHp"])
    minimum_percent = float(payload["minimumPercent"])
    maximum_percent = float(payload["maximumPercent"])
    return DamageResult(
        generation=int(payload["generation"]),
        attacker_id=str(payload["attacker"]),
        defender_id=str(payload["defender"]),
        move_id=str(payload["move"]),
        damage_rolls=rolls,
        minimum_damage=int(payload["minimumDamage"]),
        maximum_damage=int(payload["maximumDamage"]),
        defender_max_hp=defender_hp,
        minimum_percent=minimum_percent,
        maximum_percent=maximum_percent,
        description=str(payload["description"]),
        ohko_chance=calculate_ohko_chance(rolls, defender_hp),
        classification=classify_damage(minimum_percent, maximum_percent),
    )
