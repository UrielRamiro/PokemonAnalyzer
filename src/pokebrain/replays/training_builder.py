from __future__ import annotations

from pokebrain.battle.models import ActivePokemonState, BattleSideState, BattleState
from pokebrain.belief.models import BeliefState
from pokebrain.policy_calibration.models import PolicyTrainingExample
from pokebrain.replays.public_models import PartialPolicyExample, ReplaySnapshot
from pokebrain.replays.recovery_models import LegalActionQuality, LegalActionSet, ResolvedTeam
from pokebrain.search.policy import HeuristicOpponentPolicyModel
from pokebrain.team.models import EVSpread, PokemonSet


class PolicyTrainingExampleBuilder:
    def __init__(self, policy_model: HeuristicOpponentPolicyModel | None = None) -> None:
        self.policy_model = policy_model or HeuristicOpponentPolicyModel()

    def build(
        self,
        *,
        snapshot: ReplaySnapshot,
        actor_team: ResolvedTeam,
        legal_actions: LegalActionSet,
        actual_action,
    ) -> PolicyTrainingExample | PartialPolicyExample:
        if legal_actions.quality not in {LegalActionQuality.AUTHORITATIVE, LegalActionQuality.RECONSTRUCTED_COMPLETE}:
            return PartialPolicyExample(
                observed_state=snapshot.state,
                actual_action=actual_action,
                candidate_actions=legal_actions.actions or None,
                missing_information=("partial_missing_legal_actions", *legal_actions.missing_constraints),
            )
        if actual_action.action not in legal_actions.actions:
            return PartialPolicyExample(
                observed_state=snapshot.state,
                actual_action=actual_action,
                candidate_actions=legal_actions.actions,
                missing_information=("actual_action_not_in_reconstructed_legal_actions",),
            )
        observed_state = self._battle_state_for_policy(snapshot, actor_team.side)
        predicted = self.policy_model.predict(observed_state, None, legal_actions.actions)
        return PolicyTrainingExample(
            format_id=observed_state.format_id,
            rating_bucket=None,
            observed_state=observed_state,
            belief_state=BeliefState(opponent_team=()),
            legal_actions=legal_actions.actions,
            predicted_actions=predicted,
            actual_action=actual_action.action,
        )

    def _battle_state_for_policy(self, snapshot: ReplaySnapshot, actor_side: str) -> BattleState:
        opponent_side = "p1" if actor_side == "p2" else "p2"
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=snapshot.turn,
            player=_battle_side(snapshot.state, opponent_side),
            opponent=_battle_side(snapshot.state, actor_side),
            weather=snapshot.state.field.weather,
            terrain=snapshot.state.field.terrain,
        )


def _battle_side(public_state, side_id: str) -> BattleSideState:
    public_side = next((side for side in public_state.sides if side.side == side_id), None)
    public_pokemon = public_side.pokemon if public_side else ()
    team = tuple(_public_set(pokemon) for pokemon in public_pokemon) or (_fallback_set(),)
    active_index = next((index for index, pokemon in enumerate(public_pokemon) if pokemon.active), 0)
    active_set = team[min(active_index, len(team) - 1)]
    active_public = public_pokemon[active_index] if public_pokemon else None
    return BattleSideState(
        active=ActivePokemonState(active_set, _public_hp(active_public)),
        team=team,
        fainted_ids=tuple(pokemon.species_id for pokemon in public_pokemon if pokemon.fainted and pokemon.species_id),
        stealth_rock="stealthrock" in (public_side.side_conditions if public_side else ()),
        spikes_layers=1 if public_side and "spikes" in public_side.side_conditions else 0,
        toxic_spikes_layers=1 if public_side and "toxicspikes" in public_side.side_conditions else 0,
        sticky_web=bool(public_side and "stickyweb" in public_side.side_conditions),
    )


def _public_set(pokemon) -> PokemonSet:
    return PokemonSet(
        species_id=pokemon.species_id or "mew",
        nickname=None,
        item_id=pokemon.revealed_item,
        ability_id=pokemon.revealed_ability,
        level=100,
        nature=None,
        tera_type=pokemon.revealed_tera_type,
        moves=tuple(sorted(pokemon.revealed_moves)),
        evs=EVSpread(),
    )


def _fallback_set() -> PokemonSet:
    return PokemonSet("mew", None, None, None, 100, None, None, (), EVSpread())


def _public_hp(pokemon) -> int:
    if pokemon is None:
        return 100
    if pokemon.hp_current is not None:
        return pokemon.hp_current
    if pokemon.hp_fraction is not None:
        return max(0, int(round(pokemon.hp_fraction * 100)))
    return 100
