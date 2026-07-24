from __future__ import annotations

import json
from pathlib import Path

from pokebrain.battle import MoveDecisionEngine, battle_state_from_dict
from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.battle.models import ActionType, BattleAction
from pokebrain.damage import CachedDamageEngine, LruDamageCache, SearchDamageCache, ShowdownDamageEngine
from pokebrain.search import (
    ActionPruner,
    DeterministicBattleTransitionModel,
    HeuristicStateEvaluator,
    MaximinSearch,
    SearchConfig,
    SearchDecisionEngine,
)


def test_regressions_command(agent: str, cases_dir: Path) -> None:
    cases = sorted(cases_dir.glob("*.json"))
    passed = 0
    failed: list[str] = []
    for path in cases:
        with path.open("r", encoding="utf-8") as file:
            case = json.load(file)
        state = battle_state_from_dict(case["state"])
        decision = _engine(agent).decide(state)
        recommended = decision.recommended_action
        acceptable = tuple(_action_from_json(action) for action in case.get("acceptable_actions", ()))
        forbidden = tuple(_action_from_json(action) for action in case.get("forbidden_actions", ()))
        ok = (not acceptable or recommended in acceptable) and recommended not in forbidden
        if ok:
            passed += 1
        else:
            failed.append(f"{path.name}: got {_format_action(recommended)}")

    print(f"Regression cases: {passed}/{len(cases)} passed")
    if failed:
        print("")
        print("Failures:")
        for item in failed:
            print(f"- {item}")


def _engine(agent: str):
    if agent == "pokebrain-v1":
        return MoveDecisionEngine()
    if agent in {"search-v1", "search-v1-cache"}:
        damage_engine = CachedDamageEngine(
            ShowdownDamageEngine(),
            l1_cache=SearchDamageCache(),
            l2_cache=LruDamageCache(maximum_entries=50_000),
        )
        return SearchDecisionEngine(
            MaximinSearch(
                legal_action_generator=LegalActionGenerator(),
                transition_model=DeterministicBattleTransitionModel(damage_engine=damage_engine),
                state_evaluator=HeuristicStateEvaluator(),
                action_pruner=ActionPruner(),
            ),
            config=SearchConfig(maximum_depth=2, maximum_nodes=60, maximum_time_ms=400, maximum_player_actions=4, maximum_opponent_actions=4),
        )
    raise ValueError(f"Unknown regression agent: {agent}")


def _action_from_json(data: dict) -> BattleAction:
    if data["type"] == "move":
        return BattleAction(ActionType.MOVE, move_id=data.get("move_id") or data.get("moveId"))
    if data["type"] == "switch":
        return BattleAction(ActionType.SWITCH, switch_target_id=data.get("switch_target_id") or data.get("switchSpeciesId"))
    raise ValueError(f"Unknown action type: {data['type']}")


def _format_action(action: BattleAction) -> str:
    if action.move_id:
        return f"move {action.move_id}"
    return f"switch {action.switch_target_id}"
