from __future__ import annotations

from pokebrain.battle import MoveDecisionEngine
from pokebrain.battle.models import ActionType, BattleAction, BattleState


class ActionPruner:
    def __init__(self, one_turn_engine: MoveDecisionEngine | None = None) -> None:
        self.one_turn_engine = one_turn_engine or MoveDecisionEngine()
        self.last_scores: dict[BattleAction, float] = {}

    def prune(
        self,
        state: BattleState,
        actions: tuple[BattleAction, ...],
        maximum_actions: int,
    ) -> tuple[BattleAction, ...]:
        try:
            decision = self.one_turn_engine.decide(state)
            ranked = [summary.action for summary in decision.alternatives]
            self.last_scores = {summary.action: summary.average_utility for summary in decision.alternatives}
        except Exception:
            ranked = list(actions)
            self.last_scores = {}
        if len(actions) <= maximum_actions:
            return actions
        must_keep = [
            action
            for action in actions
            if action.action_type is ActionType.MOVE and action.move_id in {"rapidspin", "defog", "recover", "roost"}
        ]
        ordered: list[BattleAction] = []
        for action in (*must_keep, *ranked, *actions):
            if action in actions and action not in ordered:
                ordered.append(action)
            if len(ordered) >= maximum_actions:
                break
        return tuple(ordered)


class StaticActionPruner:
    def __init__(self) -> None:
        self.last_scores: dict[BattleAction, float] = {}

    def prune(
        self,
        state: BattleState,
        actions: tuple[BattleAction, ...],
        maximum_actions: int,
    ) -> tuple[BattleAction, ...]:
        self.last_scores = {action: self._score(action) for action in actions}
        return tuple(sorted(actions, key=lambda action: self.last_scores[action], reverse=True)[:maximum_actions])

    def _score(self, action: BattleAction) -> float:
        if action.action_type is ActionType.SWITCH:
            return 10.0
        if action.move_id in {"rapidspin", "defog", "mortalspin", "tidyup"}:
            return 35.0
        if action.move_id in {"stealthrock", "spikes", "toxicspikes", "stickyweb"}:
            return 30.0
        if action.move_id in {"recover", "roost", "slackoff", "softboiled"}:
            return 20.0
        return 25.0
