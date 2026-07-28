from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any, Protocol

from pokebrain.battle import DecisionStyle, MoveDecisionEngine
from pokebrain.battle.models import ActionSummary, ActionType, BattleAction
from pokebrain.belief import BeliefSearchConfig, BeliefSearchDecisionEngine, DecisionContext, LayeredBeliefSearchDecisionEngine, LocalUsageBeliefProvider
from pokebrain.damage import CachedDamageEngine, DamageRequest, LruDamageCache, SearchDamageCache, ShowdownDamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.battle.action_generator import LegalActionGenerator
from pokebrain.local_agent import (
    battle_state_from_decision_request,
    doubles_compound_score,
    is_doubles_compound_request,
    choose_fallback_action,
    match_legal_action,
)
from pokebrain.policy_calibration.store import load_policy_profile
from pokebrain.search import (
    ActionPruner,
    DeterministicBattleTransitionModel,
    ExpectedValueSearch,
    HeuristicOpponentPolicyModel,
    HeuristicStateEvaluator,
    MaximinSearch,
    OpponentPolicyConfig,
    PolicyProfile,
    SearchConfig,
    SearchDecisionEngine,
    StaticActionPruner,
)


DecisionRequest = dict[str, Any]
AgentAction = dict[str, Any]


class BattleAgent(Protocol):
    @property
    def name(self) -> str:
        ...

    def decide(self, request: DecisionRequest) -> AgentAction:
        ...


class PokeBrainAgent:
    name = "pokebrain-v1"

    def __init__(self, style: DecisionStyle = DecisionStyle.BALANCED) -> None:
        self.engine = MoveDecisionEngine()
        self.style = style

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        if not legal_actions:
            return {"action": {"type": "team", "slot": 1, "order": "1"}, "reasons": ["No legal action was provided."]}

        request_type = request["player"].get("requestType")
        if request_type == "team-preview":
            return {"action": _first_action(legal_actions, "team"), "reasons": ["Keeping preview order for v1."]}
        if request_type == "forced-switch":
            return {"action": _first_action(legal_actions, "switch"), "reasons": ["Forced switch request."]}

        state = battle_state_from_decision_request(request)
        decision = self.engine.decide(state, style=self.style)
        action = match_legal_action(decision.recommended_action, legal_actions) or choose_fallback_action(legal_actions)
        score = decision.alternatives[0].average_utility if decision.alternatives else None
        return {
            "action": action,
            "reasons": decision.reasons,
            "risks": decision.risks,
            "score": score,
            "alternatives": [_summary_to_json(summary) for summary in decision.alternatives],
        }


class PreviousVersionAgent(PokeBrainAgent):
    name = "previous-version"

    def __init__(self) -> None:
        super().__init__(style=DecisionStyle.CONSERVATIVE)


class SearchAgent:
    name = "search-v1"

    def __init__(self) -> None:
        data_manager = DataManager()
        shared_damage_engine = CachedDamageEngine(ShowdownDamageEngine())
        one_turn = MoveDecisionEngine(data_manager=data_manager, damage_engine=shared_damage_engine)
        search = MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(damage_engine=shared_damage_engine, data_manager=data_manager),
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            action_pruner=ActionPruner(one_turn),
        )
        self.engine = SearchDecisionEngine(
            search_engine=search,
            fallback_engine=one_turn,
            config=SearchConfig(maximum_depth=2, maximum_nodes=30, maximum_time_ms=250, maximum_player_actions=3, maximum_opponent_actions=3),
        )
        self.damage_engine = shared_damage_engine

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        if not legal_actions:
            return {"action": {"type": "team", "slot": 1, "order": "1"}, "reasons": ["No legal action was provided."]}
        request_type = request["player"].get("requestType")
        if request_type == "team-preview":
            return {"action": _first_action(legal_actions, "team"), "reasons": ["Keeping preview order for search-v1."]}
        if request_type == "forced-switch":
            return {"action": _first_action(legal_actions, "switch"), "reasons": ["Forced switch request."]}

        state = battle_state_from_decision_request(request)
        decision = self.engine.decide(state)
        action = match_legal_action(decision.recommended_action, legal_actions) or choose_fallback_action(legal_actions)
        score = decision.alternatives[0].average_utility if decision.alternatives else None
        return {
            "action": action,
            "reasons": decision.reasons,
            "risks": decision.risks,
            "score": score,
            "alternatives": [_summary_to_json(summary) for summary in decision.alternatives],
            "metrics": _search_engine_metrics(self.engine, self.damage_engine),
        }


class CachedSearchAgent:
    name = "search-v1-cache"

    def __init__(self) -> None:
        data_manager = DataManager()
        shared_damage_engine = CachedDamageEngine(
            ShowdownDamageEngine(),
            l1_cache=SearchDamageCache(),
            l2_cache=LruDamageCache(maximum_entries=50_000),
        )
        one_turn = MoveDecisionEngine(data_manager=data_manager, damage_engine=shared_damage_engine)
        search = MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(
                damage_engine=shared_damage_engine,
                data_manager=data_manager,
                enable_damage_prefetch=True,
            ),
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            action_pruner=StaticActionPruner(),
        )
        self.damage_engine = shared_damage_engine
        self.engine = SearchDecisionEngine(
            search_engine=search,
            fallback_engine=one_turn,
            config=SearchConfig(maximum_depth=2, maximum_nodes=24, maximum_time_ms=250, maximum_player_actions=3, maximum_opponent_actions=3),
        )

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        if not legal_actions:
            return {"action": {"type": "team", "slot": 1, "order": "1"}, "reasons": ["No legal action was provided."]}
        request_type = request["player"].get("requestType")
        if request_type == "team-preview":
            return {"action": _first_action(legal_actions, "team"), "reasons": ["Keeping preview order for search-v1-cache."]}
        if request_type == "forced-switch":
            return {"action": _first_action(legal_actions, "switch"), "reasons": ["Forced switch request."]}

        state = battle_state_from_decision_request(request)
        decision = self.engine.decide(state)
        action = match_legal_action(decision.recommended_action, legal_actions) or choose_fallback_action(legal_actions)
        score = decision.alternatives[0].average_utility if decision.alternatives else None
        metrics = self.damage_engine.metrics
        return {
            "action": action,
            "reasons": (
                *decision.reasons,
                f"Damage cache: {metrics.l1_cache_hits} L1 hits, {metrics.l2_cache_hits} L2 hits, {metrics.cache_misses} misses, {metrics.bridge_batches} batches.",
            ),
            "risks": decision.risks,
            "score": score,
            "alternatives": [_summary_to_json(summary) for summary in decision.alternatives],
            "metrics": {
                **_search_engine_metrics(self.engine, self.damage_engine),
                "damage_requested_calculations": metrics.requested_calculations,
                "damage_unique_calculations": metrics.unique_calculations,
                "damage_l1_cache_hits": metrics.l1_cache_hits,
                "damage_l2_cache_hits": metrics.l2_cache_hits,
                "damage_cache_misses": metrics.cache_misses,
                "damage_bridge_batches": metrics.bridge_batches,
                "damage_bridge_requests": metrics.bridge_requests,
                "damage_total_bridge_time_ms": metrics.total_bridge_time_ms,
            },
        }


class BeliefSearchAgent:
    name = "search-v2-belief"

    def __init__(self) -> None:
        data_manager = DataManager()
        shared_damage_engine = CachedDamageEngine(
            ShowdownDamageEngine(),
            l1_cache=SearchDamageCache(),
            l2_cache=LruDamageCache(maximum_entries=50_000),
        )
        one_turn = MoveDecisionEngine(data_manager=data_manager, damage_engine=shared_damage_engine)
        search = MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(
                damage_engine=shared_damage_engine,
                data_manager=data_manager,
                enable_damage_prefetch=True,
            ),
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            action_pruner=ActionPruner(one_turn),
        )
        search_engine = SearchDecisionEngine(
            search_engine=search,
            fallback_engine=one_turn,
            config=SearchConfig(maximum_depth=2, maximum_nodes=30, maximum_time_ms=250, maximum_player_actions=3, maximum_opponent_actions=3),
        )
        self.damage_engine = shared_damage_engine
        self.belief_provider = LocalUsageBeliefProvider(data_manager)
        self.engine = BeliefSearchDecisionEngine(
            search_engine=search_engine,
            belief_config=BeliefSearchConfig(maximum_scenarios=4, minimum_probability=0.05),
        )
        self.search_engine = search_engine

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        if not legal_actions:
            return {"action": {"type": "team", "slot": 1, "order": "1"}, "reasons": ["No legal action was provided."]}
        request_type = request["player"].get("requestType")
        if request_type == "team-preview":
            return {"action": _first_action(legal_actions, "team"), "reasons": ["Keeping preview order for search-v2-belief."]}
        if request_type == "forced-switch":
            return {"action": _first_action(legal_actions, "switch"), "reasons": ["Forced switch request."]}

        observed_request = dict(request)
        observed_request["opponent"] = request.get("observed_opponent") or request.get("opponent")
        state = battle_state_from_decision_request(observed_request)
        belief_state = self.belief_provider.initial_belief(state)
        decision = self.engine.decide(DecisionContext(observed_state=state, belief_state=belief_state))
        action = match_legal_action(decision.recommended_action, legal_actions) or choose_fallback_action(legal_actions)
        score = decision.alternatives[0].average_utility if decision.alternatives else None
        metrics = self.damage_engine.metrics
        return {
            "action": action,
            "reasons": decision.reasons,
            "risks": decision.risks,
            "score": score,
            "alternatives": [_summary_to_json(summary) for summary in decision.alternatives],
            "metrics": {
                **_search_engine_metrics(self.search_engine, self.damage_engine),
                "belief_scenarios": self.engine.last_scenario_count,
                "belief_assumptions": self.engine.last_assumptions,
                "damage_requested_calculations": metrics.requested_calculations,
                "damage_unique_calculations": metrics.unique_calculations,
                "damage_l1_cache_hits": metrics.l1_cache_hits,
                "damage_l2_cache_hits": metrics.l2_cache_hits,
                "damage_cache_misses": metrics.cache_misses,
                "damage_bridge_batches": metrics.bridge_batches,
                "damage_bridge_requests": metrics.bridge_requests,
                "damage_total_bridge_time_ms": metrics.total_bridge_time_ms,
            },
        }


class SharedBeliefSearchAgent(BeliefSearchAgent):
    name = "search-v2-belief-shared"

    def __init__(self) -> None:
        data_manager = DataManager()
        shared_damage_engine = CachedDamageEngine(
            ShowdownDamageEngine(),
            l1_cache=SearchDamageCache(),
            l2_cache=LruDamageCache(maximum_entries=50_000),
        )
        one_turn = MoveDecisionEngine(data_manager=data_manager, damage_engine=shared_damage_engine)
        search_config = SearchConfig(maximum_depth=2, maximum_nodes=24, maximum_time_ms=250, maximum_player_actions=3, maximum_opponent_actions=3)
        search = MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(
                damage_engine=shared_damage_engine,
                data_manager=data_manager,
                enable_damage_prefetch=True,
                reset_damage_scope_each_search=False,
            ),
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            action_pruner=StaticActionPruner(),
        )
        search_engine = SearchDecisionEngine(
            search_engine=search,
            fallback_engine=one_turn,
            config=search_config,
        )
        self.damage_engine = shared_damage_engine
        self.belief_provider = LocalUsageBeliefProvider(data_manager)
        self.engine = BeliefSearchDecisionEngine(
            search_engine=search_engine,
            belief_config=BeliefSearchConfig(maximum_scenarios=4, minimum_probability=0.05),
            damage_engine=shared_damage_engine,
            enable_global_prefetch=True,
            global_search_config=search_config,
        )
        self.search_engine = search_engine


class LayeredBeliefSearchAgent(BeliefSearchAgent):
    name = "search-v2-belief-layered"

    def __init__(self) -> None:
        data_manager = DataManager()
        shared_damage_engine = CachedDamageEngine(
            ShowdownDamageEngine(),
            l1_cache=SearchDamageCache(),
            l2_cache=LruDamageCache(maximum_entries=50_000),
        )
        one_turn = MoveDecisionEngine(data_manager=data_manager, damage_engine=shared_damage_engine)
        search_config = SearchConfig(maximum_depth=2, maximum_nodes=24, maximum_time_ms=900, maximum_player_actions=3, maximum_opponent_actions=3)
        search = MaximinSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(
                damage_engine=shared_damage_engine,
                data_manager=data_manager,
                enable_damage_prefetch=True,
                reset_damage_scope_each_search=False,
            ),
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            action_pruner=StaticActionPruner(),
        )
        search_engine = SearchDecisionEngine(
            search_engine=search,
            fallback_engine=one_turn,
            config=search_config,
        )
        self.damage_engine = shared_damage_engine
        self.belief_provider = LocalUsageBeliefProvider(data_manager)
        self.engine = LayeredBeliefSearchDecisionEngine(
            search_engine=search_engine,
            damage_engine=shared_damage_engine,
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            belief_config=BeliefSearchConfig(maximum_scenarios=4, minimum_probability=0.05),
            search_config=search_config,
        )
        self.search_engine = search_engine

    def decide(self, request: DecisionRequest) -> AgentAction:
        response = super().decide(request)
        if "metrics" not in response:
            return response
        layered_metrics = self.engine.metrics
        response["metrics"] = {
            **response["metrics"],
            "search_nodes": layered_metrics.nodes_used,
            "search_depth_reached": layered_metrics.completed_depth,
            "search_interruption_reason": "completed" if layered_metrics.completed_depth > 0 else "fallback",
            "search_fallback_used": layered_metrics.completed_depth <= 0,
            "layered_completed_depth": layered_metrics.completed_depth,
            "layered_attempted_depth": layered_metrics.attempted_depth,
            "layered_batches_by_depth": layered_metrics.batches_by_depth,
            "layered_requests_by_depth": layered_metrics.requests_by_depth,
            "layered_incomplete_layers": layered_metrics.incomplete_layers,
            "layered_timeout_before_batch": layered_metrics.timeout_before_batch,
            "layered_timeout_after_batch": layered_metrics.timeout_after_batch,
            "layered_reused_previous_pv": layered_metrics.reused_previous_pv,
            "layered_transposition_hits": layered_metrics.transposition_hits,
            "layered_planning_time_ms": layered_metrics.planning_time_ms,
            "layered_bridge_time_ms": layered_metrics.bridge_time_ms,
            "layered_resolving_time_ms": layered_metrics.resolving_time_ms,
            "layered_evaluating_time_ms": layered_metrics.evaluating_time_ms,
            "layered_ordering_time_ms": layered_metrics.ordering_time_ms,
        }
        return response


class PolicySearchAgent(BeliefSearchAgent):
    name = "search-v3-policy"

    def __init__(self, profile: PolicyProfile | None = None) -> None:
        data_manager = DataManager()
        shared_damage_engine = CachedDamageEngine(
            ShowdownDamageEngine(),
            l1_cache=SearchDamageCache(),
            l2_cache=LruDamageCache(maximum_entries=50_000),
        )
        one_turn = MoveDecisionEngine(data_manager=data_manager, damage_engine=shared_damage_engine)
        search_config = SearchConfig(maximum_depth=2, maximum_nodes=24, maximum_time_ms=1500, maximum_player_actions=3, maximum_opponent_actions=3)
        policy_config = OpponentPolicyConfig(maximum_actions=3, minimum_probability=0.05, expected_value_weight=0.75, worst_case_weight=0.25, temperature=0.8)
        policy = HeuristicOpponentPolicyModel(data_manager=data_manager, config=policy_config, profile=profile)
        search = ExpectedValueSearch(
            legal_action_generator=LegalActionGenerator(),
            transition_model=DeterministicBattleTransitionModel(
                damage_engine=shared_damage_engine,
                data_manager=data_manager,
                enable_damage_prefetch=True,
                reset_damage_scope_each_search=False,
            ),
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            opponent_policy=policy,
            action_pruner=StaticActionPruner(),
            policy_config=policy_config,
        )
        search_engine = SearchDecisionEngine(
            search_engine=search,
            fallback_engine=one_turn,
            config=search_config,
        )
        self.damage_engine = shared_damage_engine
        self.belief_provider = LocalUsageBeliefProvider(data_manager)
        self.engine = LayeredBeliefSearchDecisionEngine(
            search_engine=search_engine,
            damage_engine=shared_damage_engine,
            state_evaluator=HeuristicStateEvaluator(data_manager=data_manager),
            belief_config=BeliefSearchConfig(maximum_scenarios=4, minimum_probability=0.05),
            search_config=search_config,
        )
        self.search_engine = search_engine

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        if is_doubles_compound_request(legal_actions):
            return self._decide_doubles_compound(request, legal_actions)

        response = super().decide(request)
        if "metrics" not in response:
            return response
        layered_metrics = self.engine.metrics
        policy_metrics = _policy_metrics(self.search_engine)
        response["metrics"] = {
            **response["metrics"],
            **policy_metrics,
            "search_nodes": layered_metrics.nodes_used,
            "search_depth_reached": layered_metrics.completed_depth,
            "search_interruption_reason": "completed" if layered_metrics.completed_depth > 0 else "fallback",
            "search_fallback_used": layered_metrics.completed_depth <= 0,
            "layered_completed_depth": layered_metrics.completed_depth,
            "layered_attempted_depth": layered_metrics.attempted_depth,
            "layered_batches_by_depth": layered_metrics.batches_by_depth,
            "layered_requests_by_depth": layered_metrics.requests_by_depth,
            "layered_incomplete_layers": layered_metrics.incomplete_layers,
            "layered_timeout_before_batch": layered_metrics.timeout_before_batch,
            "layered_timeout_after_batch": layered_metrics.timeout_after_batch,
            "layered_reused_previous_pv": layered_metrics.reused_previous_pv,
            "layered_transposition_hits": layered_metrics.transposition_hits,
            "layered_planning_time_ms": layered_metrics.planning_time_ms,
            "layered_bridge_time_ms": layered_metrics.bridge_time_ms,
            "layered_resolving_time_ms": layered_metrics.resolving_time_ms,
            "layered_evaluating_time_ms": layered_metrics.evaluating_time_ms,
            "layered_ordering_time_ms": layered_metrics.ordering_time_ms,
        }
        return response

    def _decide_doubles_compound(
        self,
        request: DecisionRequest,
        legal_actions: list[dict[str, Any]],
    ) -> AgentAction:
        opponent_pressure = _opponent_compound_pressure(request)
        scored: list[tuple[float, dict[str, Any], tuple[str, ...]]] = []
        for action in legal_actions:
            base_score, base_reasons = doubles_compound_score(action, request)
            tactical_score, tactical_reasons = _vgc_compound_tactical_score(action, request)
            score = base_score + tactical_score - opponent_pressure * _passivity_penalty(action)
            scored.append(
                (
                    score,
                    action,
                    (
                        *base_reasons,
                        *tactical_reasons,
                    ),
                )
            )

        if not scored:
            return {
                "action": choose_fallback_action(legal_actions),
                "reasons": ["No compound action could be scored."],
                "metrics": {
                    "search_fallback_used": True,
                    "search_interruption_reason": "fallback",
                },
            }

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_action, best_reasons = scored[0]
        return {
            "action": best_action,
            "reasons": (
                "VGC compound search ranked legal doubles actions.",
                *best_reasons,
            ),
            "score": best_score,
            "alternatives": [
                {
                    "action": action,
                    "average_utility": score,
                    "worst_case_utility": score - opponent_pressure,
                    "best_case_utility": score,
                    "reasons": reasons,
                    "risks": (),
                }
                for score, action, reasons in scored[:5]
            ],
            "metrics": {
                "search_fallback_used": False,
                "search_interruption_reason": "vgc_compound_search",
                "search_nodes": len(scored),
                "search_depth_reached": 1,
                "layered_completed_depth": 1,
                "layered_attempted_depth": 1,
                "policy_actions_expanded": len(scored),
                "opponent_compound_pressure": opponent_pressure,
            },
        }


class CalibratedPolicySearchAgent(PolicySearchAgent):
    name = "search-v4-policy-calibrated"

    def __init__(self, profile_path: Path = Path("data/policy_profiles/gen9ou.json")) -> None:
        profile = load_policy_profile(profile_path) if profile_path.exists() else None
        super().__init__(profile=profile)


class CalibratedPolicyShadowAgent(PolicySearchAgent):
    name = "search-v3-policy-calibrated-shadow"

    def __init__(self) -> None:
        super().__init__()
        self.shadow_agent = CalibratedPolicySearchAgent()

    def decide(self, request: DecisionRequest) -> AgentAction:
        active_response = super().decide(request)
        if "metrics" not in active_response:
            return active_response
        started = time.perf_counter()
        shadow_response = self.shadow_agent.decide(request)
        shadow_ms = (time.perf_counter() - started) * 1000
        active_response["metrics"] = {
            **active_response["metrics"],
            "calibrated_shadow_action": shadow_response.get("action"),
            "calibrated_shadow_score": shadow_response.get("score"),
            "calibrated_shadow_decision_ms": shadow_ms,
            "calibrated_shadow_policy_distribution": shadow_response.get("metrics", {}).get("policy_distribution", []),
            "calibrated_shadow_policy_actions_expanded": shadow_response.get("metrics", {}).get("policy_actions_expanded", 0),
        }
        active_response["reasons"] = (
            *tuple(active_response.get("reasons", ())),
            "Calibrated policy shadow ran without controlling the active action.",
        )
        return active_response


class RandomAgent:
    name = "random"

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        if not legal_actions:
            return {"action": {"type": "team", "slot": 1, "order": "1"}, "reasons": ["No legal action was provided."]}
        return {"action": self._random.choice(legal_actions), "reasons": ["RandomAgent picked a legal action."]}


class MaxDamageAgent:
    name = "max-damage"

    def __init__(self) -> None:
        self.damage_engine = CachedDamageEngine(ShowdownDamageEngine())

    def decide(self, request: DecisionRequest) -> AgentAction:
        legal_actions = request.get("legal_actions", [])
        move_actions = [action for action in legal_actions if action.get("type") == "move"]
        if not move_actions:
            return {"action": choose_fallback_action(legal_actions), "reasons": ["No legal damaging action was available."]}

        state = battle_state_from_decision_request(request)
        scored: list[tuple[float, dict[str, Any]]] = []
        for action in move_actions:
            move_id = action.get("moveId")
            if not move_id:
                continue
            try:
                damage = self.damage_engine.calculate(
                    DamageRequest(
                        generation=state.generation,
                        attacker=state.player.active.set_data,
                        defender=state.opponent.active.set_data,
                        move_id=move_id,
                    )
                )
                scored.append(((damage.minimum_percent + damage.maximum_percent) / 2, action))
            except Exception:
                scored.append((0.0, action))

        if not scored:
            return {"action": choose_fallback_action(legal_actions), "reasons": ["Damage scoring failed for every move."]}
        score, action = max(scored, key=lambda item: item[0])
        return {"action": action, "reasons": [f"Selected highest expected damage ({score:.1f}%)."], "score": score}


def _vgc_compound_tactical_score(action: dict[str, Any], request: DecisionRequest) -> tuple[float, tuple[str, ...]]:
    choices = action.get("choices", ())
    score = 0.0
    reasons: list[str] = []
    move_ids = {str(choice.get("moveId", "")).lower() for choice in choices if choice.get("type") == "move"}
    switch_count = sum(1 for choice in choices if choice.get("type") == "switch")
    protect_count = sum(1 for move_id in move_ids if move_id in _PROTECT_MOVES)

    if switch_count:
        score += 8.0 * switch_count
        reasons.append("Considered switching as VGC positioning.")
    if switch_count >= 2:
        score -= 18.0
        reasons.append("Penalized fully defensive double switch.")

    if protect_count == 1 and _opponent_has_priority_pressure(request):
        score += 14.0
        reasons.append("Protected one slot against priority/Fake Out pressure.")
    elif protect_count >= 2:
        score -= 18.0
        reasons.append("Penalized passive double Protect in compound search.")

    if _has_spread_damage(move_ids):
        score += 12.0
        reasons.append("Valued spread damage.")
    if move_ids & _SPEED_CONTROL_MOVES:
        score += 12.0
        reasons.append("Valued speed control.")
    if move_ids & _REDIRECTION_MOVES:
        score += 9.0
        reasons.append("Valued redirection support.")
    if move_ids & _DISRUPTION_MOVES:
        score += 8.0
        reasons.append("Valued disruption.")
    if move_ids & _SETUP_MOVES and _opponent_compound_pressure(request) >= 35.0:
        score -= 16.0
        reasons.append("Penalized setup under high immediate pressure.")

    low_hp_attackers = _low_hp_active_slots(request)
    for choice in choices:
        if choice.get("type") != "move":
            continue
        active_slot = int(choice.get("activeSlot") or 1)
        move_id = str(choice.get("moveId", "")).lower()
        if active_slot in low_hp_attackers and move_id not in _PROTECT_MOVES:
            score -= 8.0
            reasons.append("Penalized exposing a low-HP active slot.")

    return score, tuple(dict.fromkeys(reasons))


def _opponent_compound_pressure(request: DecisionRequest) -> float:
    opponent = request.get("opponent") or request.get("observed_opponent") or {}
    pressure = 0.0
    for pokemon in opponent.get("team", ()):
        if pokemon.get("fainted"):
            continue
        moves = {str(move).lower() for move in pokemon.get("moves", ())}
        if moves & {"fakeout", "suckerpunch", "aquajet", "accelerock", "quickattack", "shadowsneak"}:
            pressure += 16.0
        if moves & _SPEED_CONTROL_MOVES:
            pressure += 12.0
        if moves & _REDIRECTION_MOVES:
            pressure += 8.0
        if moves & _SPREAD_DAMAGE_MOVES:
            pressure += 10.0
        if pokemon.get("active"):
            pressure += 6.0
    return min(60.0, pressure)


def _passivity_penalty(action: dict[str, Any]) -> float:
    choices = action.get("choices", ())
    passive = 0
    for choice in choices:
        if choice.get("type") == "switch":
            passive += 1
        elif choice.get("type") == "move" and str(choice.get("moveId", "")).lower() in _PASSIVE_MOVES:
            passive += 1
    return 0.18 * passive


def _opponent_has_priority_pressure(request: DecisionRequest) -> bool:
    opponent = request.get("opponent") or request.get("observed_opponent") or {}
    priority = {"fakeout", "suckerpunch", "aquajet", "accelerock", "quickattack", "shadowsneak"}
    return any(
        priority & {str(move).lower() for move in pokemon.get("moves", ())}
        for pokemon in opponent.get("team", ())
        if not pokemon.get("fainted")
    )


def _low_hp_active_slots(request: DecisionRequest) -> set[int]:
    slots: set[int] = set()
    active_seen = 0
    for pokemon in request.get("player", {}).get("team", ()):
        if not pokemon.get("active"):
            continue
        active_seen += 1
        if _condition_fraction(str(pokemon.get("condition", "1/1"))) <= 0.35:
            slots.add(active_seen)
    return slots


def _condition_fraction(condition: str) -> float:
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


def _has_spread_damage(move_ids: set[str]) -> bool:
    return bool(move_ids & _SPREAD_DAMAGE_MOVES)


_PROTECT_MOVES = {"protect", "detect", "spikyshield", "kingsshield", "banefulbunker"}
_PASSIVE_MOVES = _PROTECT_MOVES | {"calmmind", "swordsdance", "nastyplot", "dragondance", "lifedew"}
_SPEED_CONTROL_MOVES = {"tailwind", "trickroom", "icywind", "electroweb", "thunderwave", "rocktomb"}
_REDIRECTION_MOVES = {"followme", "ragepowder"}
_DISRUPTION_MOVES = {"fakeout", "yawn", "spore", "sleeppowder", "willowisp", "taunt", "partingshot"}
_SETUP_MOVES = {"swordsdance", "nastyplot", "calmmind", "dragondance"}
_SPREAD_DAMAGE_MOVES = {
    "heatwave",
    "rockslide",
    "earthquake",
    "hypervoice",
    "dazzlinggleam",
    "blizzard",
    "muddywater",
    "surf",
    "discharge",
    "eruption",
    "waterdamage",
    "snarl",
    "icywind",
    "electroweb",
}


def create_battle_agent(name: str, seed: int | None = None) -> BattleAgent:
    if name in {"pokebrain", "pokebrain-v1"}:
        return PokeBrainAgent()
    if name in {"previous-version", "pokebrain-previous"}:
        return PreviousVersionAgent()
    if name == "search-v1":
        return SearchAgent()
    if name == "search-v1-cache":
        return CachedSearchAgent()
    if name == "search-v2-belief":
        return BeliefSearchAgent()
    if name == "search-v2-belief-shared":
        return SharedBeliefSearchAgent()
    if name == "search-v2-belief-layered":
        return LayeredBeliefSearchAgent()
    if name == "search-v3-policy":
        return PolicySearchAgent()
    if name == "search-v3-policy-calibrated-shadow":
        return CalibratedPolicyShadowAgent()
    if name == "search-v4-policy-calibrated":
        return CalibratedPolicySearchAgent()
    if name == "random":
        return RandomAgent(seed)
    if name == "max-damage":
        return MaxDamageAgent()
    raise ValueError(f"Unknown benchmark agent: {name}")


def _search_engine_metrics(engine: SearchDecisionEngine, shared_damage_engine: CachedDamageEngine | None = None) -> dict[str, Any]:
    result = engine.last_search_result
    metrics: dict[str, Any] = {
        "search_nodes": result.explored_nodes if result is not None else 0,
        "search_depth_reached": result.depth_reached if result is not None else 0,
        "search_interruption_reason": result.interruption_reason if result is not None else engine.last_fallback_reason or "fallback",
        "search_fallback_used": engine.last_fallback_used,
    }
    if shared_damage_engine is not None:
        damage = shared_damage_engine.metrics
        metrics.update(
            {
                "damage_requested_calculations": damage.requested_calculations,
                "damage_unique_calculations": damage.unique_calculations,
                "damage_l1_cache_hits": damage.l1_cache_hits,
                "damage_same_scenario_hits": damage.same_scenario_hits,
                "damage_cross_scenario_hits": damage.cross_scenario_hits,
                "damage_l2_cache_hits": damage.l2_cache_hits,
                "damage_cache_misses": damage.cache_misses,
                "damage_bridge_batches": damage.bridge_batches,
                "damage_bridge_requests": damage.bridge_requests,
                "damage_total_bridge_time_ms": damage.total_bridge_time_ms,
            }
        )
    return metrics


def _policy_metrics(engine: SearchDecisionEngine) -> dict[str, Any]:
    search = getattr(engine, "search_engine", None)
    distribution = getattr(search, "last_policy_distribution", ())
    return {
        "policy_actions_expanded": getattr(search, "last_policy_actions_expanded", 0),
        "policy_distribution": [
            {
                "action": _battle_action_to_json(item.action),
                "probability": item.probability,
                "policy_score": item.policy_score,
                "reasons": [
                    {
                        "code": reason.code,
                        "contribution": reason.contribution,
                        "description": reason.description,
                    }
                    for reason in item.reasons
                ],
            }
            for item in distribution
        ],
    }


def _first_action(legal_actions: list[dict[str, Any]], action_type: str) -> dict[str, Any]:
    return next((action for action in legal_actions if action.get("type") == action_type), legal_actions[0])


def _summary_to_json(summary: ActionSummary) -> dict[str, Any]:
    return {
        "action": _battle_action_to_json(summary.action),
        "average_utility": summary.average_utility,
        "worst_case_utility": summary.worst_case_utility,
        "best_case_utility": summary.best_case_utility,
        "reasons": summary.reasons,
        "risks": summary.risks,
    }


def _battle_action_to_json(action: BattleAction) -> dict[str, Any]:
    if action.action_type is ActionType.MOVE:
        return {"type": "move", "moveId": action.move_id}
    return {"type": "switch", "switchSpeciesId": action.switch_target_id}
