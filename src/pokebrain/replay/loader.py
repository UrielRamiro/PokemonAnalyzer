from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pokebrain.battle.models import ActionSummary, ActionType, BattleAction, BattleState
from pokebrain.battle_protocol.parser import parse_protocol_line
from pokebrain.local_agent import battle_state_from_decision_request
from pokebrain.replay.models import BattleReplay, DecisionRecord


class ReplayLoader:
    def load(self, battle_directory: Path) -> BattleReplay:
        result = _load_json(battle_directory / "result.json")
        states = _load_states(battle_directory / "states.jsonl")
        decisions = tuple(self._load_decisions(battle_directory, states))
        events = tuple(_load_events(battle_directory / "protocol.log"))
        return BattleReplay(
            battle_id=result.get("battle_id", battle_directory.name),
            initial_state=decisions[0].battle_state if decisions else None,
            events=events,
            decisions=decisions,
            winner=result.get("winner"),
            battle_directory=str(battle_directory),
        )

    def _load_decisions(
        self,
        battle_directory: Path,
        states: dict[tuple[int, str], dict[str, Any]],
    ) -> list[DecisionRecord]:
        records: list[DecisionRecord] = []
        battle_id = battle_directory.name
        decisions_path = battle_directory / "decisions.jsonl"
        if not decisions_path.exists():
            return records
        with decisions_path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                data = json.loads(line)
                if "selected_action" not in data:
                    continue
                turn = int(data.get("turn", 0))
                player_id = str(data.get("player_id", "p1"))
                state_request = states.get((turn, player_id)) or _nearest_state(states, turn, player_id)
                if state_request is None:
                    continue
                battle_state = battle_state_from_decision_request(state_request)
                selected_action = _action_from_json(data["selected_action"])
                alternatives = tuple(_summary_from_json(item) for item in data.get("alternatives", ()))
                selected_summary = _selected_summary(selected_action, data, alternatives)
                records.append(
                    DecisionRecord(
                        battle_id=battle_id,
                        turn=turn,
                        player_id=player_id,
                        battle_state=battle_state,
                        legal_actions=tuple(_action_from_json(action) for action in data.get("legal_actions", ())),
                        selected_action=selected_action,
                        selected_evaluation=selected_summary,
                        alternative_evaluations=alternatives,
                        decision_time_ms=float(data.get("decision_time_ms") or 0.0),
                        reasons=tuple(data.get("reasons", ())),
                        risks=tuple(data.get("risks", ())),
                    )
                )
        return records


class ReplayStateBuilder:
    def state_at_turn(self, replay: BattleReplay, turn: int) -> BattleState:
        candidates = [record for record in replay.decisions if record.turn <= turn]
        if candidates:
            return candidates[-1].battle_state
        if replay.initial_state is None:
            raise ValueError("Replay has no reconstructable BattleState.")
        return replay.initial_state


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _load_states(path: Path) -> dict[tuple[int, str], dict[str, Any]]:
    states: dict[tuple[int, str], dict[str, Any]] = {}
    if not path.exists():
        return states
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            data = json.loads(line)
            request = data.get("request")
            if not request:
                continue
            key = (int(data.get("turn", 0)), str(data.get("player_id", request.get("playerId", "p1"))))
            states[key] = {
                "type": "decision-request",
                "battle_id": path.parent.name,
                "format_id": "gen9ou",
                "generation": 9,
                "turn": key[0],
                "player_id": key[1],
                "player": request,
                "opponent": states.get((key[0], "p2" if key[1] == "p1" else "p1"), {}).get("player"),
                "legal_actions": request.get("legalActions", ()),
            }
    _fill_opponents(states)
    return states


def _fill_opponents(states: dict[tuple[int, str], dict[str, Any]]) -> None:
    for (turn, player_id), state in list(states.items()):
        opponent_id = "p2" if player_id == "p1" else "p1"
        opponent = states.get((turn, opponent_id))
        if opponent:
            state["opponent"] = opponent["player"]


def _nearest_state(states: dict[tuple[int, str], dict[str, Any]], turn: int, player_id: str) -> dict[str, Any] | None:
    candidates = [
        (state_turn, state)
        for (state_turn, state_player), state in states.items()
        if state_player == player_id and state_turn <= turn
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[-1][1]


def _load_events(path: Path):
    if not path.exists():
        return ()
    events = []
    with path.open("r", encoding="utf-8") as file:
        for raw in file.read().splitlines():
            try:
                event = parse_protocol_line(raw)
            except (IndexError, ValueError):
                continue
            if event is not None:
                events.append(event)
    return events


def _action_from_json(data: dict[str, Any]) -> BattleAction:
    action_type = data.get("type")
    if action_type == "move":
        move_id = data.get("moveId") or data.get("move_id")
        return BattleAction(ActionType.MOVE, move_id=move_id)
    if action_type == "switch":
        switch_target_id = data.get("switchSpeciesId") or data.get("switch_target_id")
        return BattleAction(ActionType.SWITCH, switch_target_id=switch_target_id)
    return BattleAction(ActionType.MOVE, move_id=str(action_type or "unknown"), action_id=_compound_action_id(data))


def _simple_action_id(data: dict[str, Any]) -> str:
    action_type = str(data.get("type") or "unknown")
    if action_type == "move":
        parts = [
            "move",
            str(data.get("moveId") or data.get("move_id") or ""),
            str(data.get("slot") or ""),
            str(data.get("target") or ""),
            "tera" if data.get("terastallize") else "",
        ]
        return ":".join(part for part in parts if part)
    if action_type == "switch":
        return f"switch:{data.get('switchSpeciesId') or data.get('switch_target_id') or data.get('slot') or ''}"
    return action_type


def _compound_action_id(data: dict[str, Any]) -> str:
    action_type = str(data.get("type") or "unknown")
    if action_type != "compound":
        return action_type
    return "compound:" + "+".join(_simple_action_id(choice) for choice in data.get("choices", ()))


def _summary_from_json(data: dict[str, Any]) -> ActionSummary:
    return ActionSummary(
        action=_action_from_json(data["action"]),
        average_utility=float(data.get("average_utility", data.get("score", 0.0)) or 0.0),
        worst_case_utility=float(data.get("worst_case_utility", data.get("score", 0.0)) or 0.0),
        best_case_utility=float(data.get("best_case_utility", data.get("score", 0.0)) or 0.0),
        reasons=tuple(data.get("reasons", ())),
        risks=tuple(data.get("risks", ())),
    )


def _selected_summary(
    selected_action: BattleAction,
    data: dict[str, Any],
    alternatives: tuple[ActionSummary, ...],
) -> ActionSummary:
    for alternative in alternatives:
        if alternative.action == selected_action:
            return alternative
    score = float(data.get("score") or data.get("selected_score") or 0.0)
    return ActionSummary(
        action=selected_action,
        average_utility=score,
        worst_case_utility=score,
        best_case_utility=score,
        reasons=tuple(data.get("reasons", ())),
        risks=tuple(data.get("risks", ())),
    )
