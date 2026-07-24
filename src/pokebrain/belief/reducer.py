from __future__ import annotations

from dataclasses import replace

from pokebrain.battle_protocol.events import AbilityEvent, BattleEvent, DamageEvent, ItemEvent, MoveEvent, TerastallizeEvent
from pokebrain.battle_protocol.identifiers import species_id_from_identifier
from pokebrain.belief.distribution import collapse_to, normalize, remove_value
from pokebrain.belief.models import BeliefState, PokemonBelief, WeightedValue


HAZARD_SOURCES = {"Stealth Rock", "Spikes", "Toxic Spikes", "stickyweb", "Sticky Web"}


class BeliefStateReducer:
    def apply(self, belief_state: BeliefState, event: BattleEvent) -> BeliefState:
        species_id = _species_from_event(event)
        if species_id is None:
            return belief_state
        return replace(
            belief_state,
            opponent_team=tuple(
                self._apply_to_belief(belief, event)
                if belief.species_id == species_id
                else belief
                for belief in belief_state.opponent_team
            ),
        )

    def _apply_to_belief(self, belief: PokemonBelief, event: BattleEvent) -> PokemonBelief:
        if isinstance(event, MoveEvent):
            return reveal_move(belief, event.move_id)
        if isinstance(event, ItemEvent):
            return reveal_item(belief, event.item_id)
        if isinstance(event, AbilityEvent):
            return reveal_ability(belief, event.ability_id)
        if isinstance(event, TerastallizeEvent):
            return reveal_tera_type(belief, event.tera_type)
        if isinstance(event, DamageEvent) and event.source in HAZARD_SOURCES:
            return replace(belief, possible_items=remove_value(belief.possible_items, "heavydutyboots"))
        return belief


def reveal_move(belief: PokemonBelief, move_id: str) -> PokemonBelief:
    existing = {item.value: item.probability for item in belief.possible_moves}
    existing[move_id] = max(existing.get(move_id, 0.0), 1.0)
    return replace(
        belief,
        possible_moves=normalize(tuple(WeightedValue(value, probability) for value, probability in existing.items())),
        revealed_moves=belief.revealed_moves | {move_id},
    )


def reveal_item(belief: PokemonBelief, item_id: str) -> PokemonBelief:
    return replace(belief, possible_items=collapse_to(item_id), revealed_item=item_id)


def reveal_ability(belief: PokemonBelief, ability_id: str) -> PokemonBelief:
    return replace(belief, possible_abilities=collapse_to(ability_id), revealed_ability=ability_id)


def reveal_tera_type(belief: PokemonBelief, tera_type: str) -> PokemonBelief:
    return replace(belief, possible_tera_types=collapse_to(tera_type), revealed_tera_type=tera_type)


def _species_from_event(event: BattleEvent) -> str | None:
    identifier = getattr(event, "pokemon_identifier", None)
    if not identifier:
        return None
    return species_id_from_identifier(str(identifier))
