from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from typing import Any

from pokebrain.battle import (
    ActivePokemonState,
    BattleSideState,
    BattleState,
    DecisionStyle,
    MoveDecisionEngine,
)
from pokebrain.battle.models import ActionType
from pokebrain.team.models import EVSpread, PokemonSet
from pokebrain.utils import to_id


class LocalBattleAgent:
    def __init__(self, agent_name: str = "pokebrain-v1", seed: int | None = None) -> None:
        from pokebrain.benchmark.agents import create_battle_agent

        self.agent_name = agent_name
        self.agent = create_battle_agent(agent_name, seed=seed)

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        message_type = message.get("type")
        if message_type == "hello":
            if "agentName" in message:
                from pokebrain.benchmark.agents import create_battle_agent

                self.agent_name = str(message["agentName"])
                self.agent = create_battle_agent(self.agent_name, seed=_seed_from_message(message))
            return {"type": "hello", "ok": True}
        if message_type == "shutdown":
            return {"type": "shutdown", "ok": True}
        if message_type != "decision-request":
            return {"type": "error", "error": f"Unsupported message type: {message_type}"}
        return self.decide(message)

    def decide(self, request: dict[str, Any]) -> dict[str, Any]:
        started_at = time.perf_counter()
        legal_actions = request.get("legal_actions", [])
        if is_doubles_compound_request(legal_actions):
            action, score, reasons = choose_doubles_compound_action(legal_actions, request)
            return self._decision(
                action,
                ["Fast doubles bridge policy selected a legal compound action.", *reasons],
                score=score,
                metrics={
                    "search_fallback_used": True,
                    "search_interruption_reason": "doubles_bridge_policy",
                },
                decision_time_ms=(time.perf_counter() - started_at) * 1000,
            )
        try:
            agent_decision = self.agent.decide(request)
            return self._decision(
                action=agent_decision["action"],
                reasons=agent_decision.get("reasons", ()),
                risks=agent_decision.get("risks", ()),
                score=agent_decision.get("score"),
                alternatives=agent_decision.get("alternatives", ()),
                metrics=agent_decision.get("metrics", {}),
                decision_time_ms=(time.perf_counter() - started_at) * 1000,
            )
        except Exception as error:
            return self._decision(
                choose_fallback_action(legal_actions),
                [f"Fallback action after agent error: {error}"],
                metrics={
                    "search_fallback_used": True,
                    "search_interruption_reason": "fallback",
                    "agent_error": str(error),
                },
                decision_time_ms=(time.perf_counter() - started_at) * 1000,
            )

    def _decision(
        self,
        action: dict[str, Any],
        reasons: tuple[str, ...] | list[str],
        risks: tuple[str, ...] | list[str] = (),
        score: float | None = None,
        alternatives=(),
        metrics: dict[str, Any] | None = None,
        decision_time_ms: float | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "decision",
            "action": action,
            "reasons": tuple(reasons),
            "risks": tuple(risks),
            "score": score,
            "alternatives": tuple(alternatives),
            "metrics": metrics or {},
            "decision_time_ms": decision_time_ms,
        }


def battle_state_from_decision_request(request: dict[str, Any]) -> BattleState:
    player = side_state_from_normalized_request(request["player"])
    opponent_request = request.get("opponent") or empty_opponent_request()
    opponent = side_state_from_normalized_request(opponent_request)
    return BattleState(
        generation=int(request.get("generation", 9)),
        format_id=str(request.get("format_id", "gen9ou")),
        turn=int(request.get("turn", 1)),
        player=player,
        opponent=opponent,
    )


def side_state_from_normalized_request(request: dict[str, Any]) -> BattleSideState:
    team = tuple(pokemon_set_from_side_pokemon(pokemon) for pokemon in request.get("team", ()))
    active_index = next(
        (index for index, pokemon in enumerate(request.get("team", ())) if pokemon.get("active")),
        0,
    )
    if team:
        active_set = team[active_index]
        active_source = request.get("team", [])[active_index]
    else:
        active_set = PokemonSet("mew", None, None, None, 100, None, None, ("tackle",), EVSpread())
        active_source = {"condition": "1/1"}
    return BattleSideState(
        active=ActivePokemonState(
            set_data=active_set,
            current_hp=current_hp_from_condition(str(active_source.get("condition", "1/1"))),
        ),
        team=team or (active_set,),
        fainted_ids=tuple(
            pokemon["speciesId"]
            for pokemon in request.get("team", ())
            if pokemon.get("fainted")
        ),
    )


def pokemon_set_from_side_pokemon(pokemon: dict[str, Any]) -> PokemonSet:
    return PokemonSet(
        species_id=to_id(str(pokemon["speciesId"])),
        nickname=None,
        item_id=optional_id(pokemon.get("itemId")),
        ability_id=optional_id(pokemon.get("abilityId")),
        level=level_from_details(str(pokemon.get("details", ""))),
        nature=None,
        tera_type=pokemon.get("teraType"),
        moves=tuple(to_id(move) for move in pokemon.get("moves", ())),
        evs=EVSpread(),
    )


def match_legal_action(recommended_action, legal_actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if recommended_action.action_type == ActionType.MOVE:
        for action in legal_actions:
            if action.get("type") == "move" and action.get("moveId") == recommended_action.move_id:
                return action
    if recommended_action.action_type == ActionType.SWITCH:
        for action in legal_actions:
            if action.get("type") == "switch" and action.get("switchSpeciesId") == recommended_action.switch_target_id:
                return action
    return None


def choose_fallback_action(legal_actions: list[dict[str, Any]]) -> dict[str, Any]:
    if not legal_actions:
        return {"type": "default"}
    for action in legal_actions:
        if action.get("type") == "compound":
            return action
    for action in legal_actions:
        if action.get("type") == "default":
            return action
    for action_type in ("move", "switch", "team"):
        for action in legal_actions:
            if action.get("type") == action_type:
                return action
    return legal_actions[0]


def is_doubles_compound_request(legal_actions: list[dict[str, Any]]) -> bool:
    return bool(legal_actions) and all(action.get("type") == "compound" for action in legal_actions)


def choose_doubles_compound_action(legal_actions: list[dict[str, Any]], request: dict[str, Any]) -> tuple[dict[str, Any], float, tuple[str, ...]]:
    scored = tuple(
        (
            action,
            *doubles_compound_score(action, request),
        )
        for action in legal_actions
    )
    action, score, reasons = max(scored, key=lambda item: item[1])
    return action, score, reasons


def doubles_compound_score(action: dict[str, Any], request: dict[str, Any]) -> tuple[float, tuple[str, ...]]:
    choices = action.get("choices", ())
    score = 0.0
    reasons: list[str] = []
    for choice in choices:
        if choice.get("type") == "move":
            move_score, move_reasons = doubles_move_score(str(choice.get("moveId", "")), choice, choices, request)
            score += move_score
            reasons.extend(move_reasons)
            if choice.get("terastallize"):
                score += 3.0
        elif choice.get("type") == "switch":
            score += 12.0
    if _all_live_slots_protect(choices, request):
        score -= 48.0
        reasons.append("Avoided overvaluing double Protect.")
    return score, tuple(reasons)


def doubles_move_score(move_id: str, choice: dict[str, Any] | None = None, choices=(), request: dict[str, Any] | None = None) -> tuple[float, tuple[str, ...]]:
    move_id = to_id(move_id)
    if move_id in {"protect", "detect", "spikyshield", "kingsshield", "banefulbunker"}:
        return doubles_protect_score(choice or {}, choices, request or {})
    if move_id == "fakeout":
        return 85.0, ("Prioritized Fake Out pressure.",)
    if move_id in {"tailwind", "trickroom", "icywind", "electroweb", "thunderwave", "rocktomb"}:
        return 70.0, ("Prioritized speed control.",)
    if move_id in {"followme", "ragepowder"}:
        return 65.0, ("Prioritized redirection.",)
    if move_id in {"wideguard", "quickguard"}:
        return 45.0, ("Considered team protection.",)
    if move_id in {"swordsdance", "nastyplot", "calmmind", "dragondance"}:
        return 35.0, ("Considered setup.",)
    if move_id in {"yawn", "spore", "sleeppowder", "willowisp", "taunt"}:
        return 55.0, ("Considered disruption.",)
    return 50.0, ()


def doubles_protect_score(choice: dict[str, Any], choices, request: dict[str, Any]) -> tuple[float, tuple[str, ...]]:
    score = 38.0
    reasons = ["Valued Protect as a VGC positioning option."]
    active_slot = int(choice.get("activeSlot") or 1)
    hp_fraction = _active_hp_fraction(request, active_slot)
    if hp_fraction <= 0.35:
        score += 24.0
        reasons.append("Boosted Protect for low HP.")
    elif hp_fraction <= 0.6:
        score += 8.0
        reasons.append("Boosted Protect for moderate chip risk.")
    elif hp_fraction >= 0.85:
        score -= 12.0
        reasons.append("Reduced Protect at high HP without clear danger.")
    if _opponent_revealed_move(request, "fakeout") and active_slot in {1, 2}:
        score += 12.0
        reasons.append("Boosted Protect against revealed Fake Out pressure.")
    if _partner_has_proactive_choice(active_slot, choices):
        score += 4.0
        reasons.append("Boosted Protect while partner advances position.")
    return score, tuple(reasons)


def _active_hp_fraction(request: dict[str, Any], active_slot: int) -> float:
    active_seen = 0
    for pokemon in request.get("player", {}).get("team", ()):
        if not pokemon.get("active"):
            continue
        active_seen += 1
        if active_seen != active_slot:
            continue
        condition = str(pokemon.get("condition", "100/100"))
        if condition.endswith(" fnt"):
            return 0.0
        hp_text = condition.split()[0]
        if "/" not in hp_text:
            return 1.0
        current, maximum = hp_text.split("/", 1)
        try:
            return max(0.0, min(1.0, float(current) / max(1.0, float(maximum))))
        except ValueError:
            return 1.0
    return 1.0


def _opponent_revealed_move(request: dict[str, Any], move_id: str) -> bool:
    wanted = to_id(move_id)
    opponent = request.get("opponent") or request.get("observed_opponent") or {}
    return any(
        wanted in {to_id(move) for move in pokemon.get("moves", ())}
        for pokemon in opponent.get("team", ())
    )


def _partner_has_proactive_choice(active_slot: int, choices) -> bool:
    for choice in choices:
        if int(choice.get("activeSlot") or 0) == active_slot:
            continue
        if choice.get("type") != "move":
            continue
        move_id = to_id(str(choice.get("moveId", "")))
        if move_id and move_id not in {"protect", "detect", "spikyshield", "kingsshield", "banefulbunker"}:
            return True
    return False


def _all_live_slots_protect(choices, request: dict[str, Any]) -> bool:
    move_choices = [choice for choice in choices if choice.get("type") == "move"]
    if len(move_choices) < 2:
        return False
    return all(to_id(str(choice.get("moveId", ""))) in {"protect", "detect", "spikyshield", "kingsshield", "banefulbunker"} for choice in move_choices)


def current_hp_from_condition(condition: str) -> int:
    if condition.endswith(" fnt"):
        return 0
    hp_text = condition.split()[0]
    if "/" in hp_text:
        return int(float(hp_text.split("/", 1)[0]))
    return int(float(hp_text))


def level_from_details(details: str) -> int:
    for part in details.split(","):
        part = part.strip()
        if part.startswith("L") and part[1:].isdigit():
            return int(part[1:])
    return 100


def optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    return to_id(value)


def empty_opponent_request() -> dict[str, Any]:
    return {
        "team": [
            {
                "speciesId": "mew",
                "condition": "1/1",
                "active": True,
                "moves": ["tackle"],
            }
        ]
    }


def main() -> None:
    agent = LocalBattleAgent()
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        response = agent.handle(message)
        sys.stdout.write(f"{json.dumps(response, default=_json_default)}\n")
        sys.stdout.flush()
        if message.get("type") == "shutdown":
            break


def _json_default(value):
    try:
        return asdict(value)
    except TypeError:
        return str(value)


def _seed_from_message(message: dict[str, Any]) -> int | None:
    seed = message.get("seed")
    if isinstance(seed, list):
        return sum(int(value) for value in seed)
    if seed is None:
        return None
    return int(seed)


if __name__ == "__main__":
    main()
