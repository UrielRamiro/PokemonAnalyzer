from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.battle import (
    ActionSummary,
    ActionType,
    ActivePokemonState,
    BattleAction,
    BattleSideState,
    BattleState,
    DecisionStyle,
    LegalActionGenerator,
    MoveDecisionEngine,
)
from pokebrain.battle.decision import _style_score
from pokebrain.battle.evaluators import SwitchEvaluator
from pokebrain.damage import CachedDamageEngine, ShowdownDamageEngine
from pokebrain.data.manager import DataManager
from pokebrain.team.models import EVSpread, PokemonSet


class MoveDecisionEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data_manager = DataManager(ROOT_DIR / "data" / "database" / "pokemon.db")
        cls.damage_engine = CachedDamageEngine(ShowdownDamageEngine(root_dir=ROOT_DIR))

    def setUp(self) -> None:
        self.engine = MoveDecisionEngine(
            data_manager=self.data_manager,
            damage_engine=self.damage_engine,
        )

    def test_recommends_guaranteed_ko(self) -> None:
        state = self._state(
            player_active=self._set(
                "greattusk",
                ability_id="protosynthesis",
                item_id="choiceband",
                nature="Adamant",
                evs=EVSpread(attack=252),
                moves=("headlongrush",),
            ),
            opponent_active=self._set(
                "kingambit",
                ability_id="supremeoverlord",
                evs=EVSpread(hp=252),
                moves=("suckerpunch",),
            ),
            opponent_hp=220,
        )

        decision = self.engine.decide(state)

        self.assertEqual(decision.recommended_action.action_type, ActionType.MOVE)
        self.assertEqual(decision.recommended_action.move_id, "headlongrush")

    def test_avoids_move_into_immunity(self) -> None:
        garchomp = self._set("garchomp", evs=EVSpread(attack=252), moves=("earthquake",))
        kingambit = self._set(
            "kingambit",
            ability_id="supremeoverlord",
            item_id="blackglasses",
            evs=EVSpread(hp=252, attack=252),
            moves=("kowtowcleave",),
        )
        state = self._state(
            player_active=garchomp,
            player_team=(garchomp, kingambit),
            opponent_active=self._set("rotomwash", ability_id="levitate", moves=("hydropump",)),
        )

        decision = self.engine.decide(state)

        self.assertNotEqual(decision.recommended_action.move_id, "earthquake")
        self.assertEqual(decision.recommended_action.action_type, ActionType.SWITCH)

    def test_recommends_switch_when_current_pokemon_is_threatened(self) -> None:
        garchomp = self._set("garchomp", moves=("swordsdance",))
        corviknight = self._set(
            "corviknight",
            item_id="leftovers",
            ability_id="pressure",
            evs=EVSpread(hp=252, defense=252),
            moves=("bodypress", "roost"),
        )
        state = self._state(
            player_active=garchomp,
            player_team=(garchomp, corviknight),
            player_hp=80,
            opponent_active=self._set(
                "weavile",
                ability_id="pressure",
                nature="Jolly",
                evs=EVSpread(attack=252, speed=252),
                moves=("icespinner",),
            ),
        )

        decision = self.engine.decide(state, style=DecisionStyle.CONSERVATIVE)

        self.assertEqual(decision.recommended_action.action_type, ActionType.SWITCH)
        self.assertEqual(decision.recommended_action.switch_target_id, "corviknight")

    def test_does_not_switch_when_trapped(self) -> None:
        active = self._set("garchomp", moves=("earthquake",))
        bench = self._set("kingambit", moves=("kowtowcleave",))
        state = self._state(
            player_active=active,
            player_team=(active, bench),
            opponent_active=self._set("weavile", moves=("icespinner",)),
            trapped=True,
        )

        actions = LegalActionGenerator().generate(state)

        self.assertEqual(tuple(action.action_type for action in actions), (ActionType.MOVE,))

    def test_accounts_for_entry_hazards(self) -> None:
        evaluator = SwitchEvaluator(self.damage_engine, self.data_manager)
        charizard = self._set("charizard", item_id=None, moves=("flamethrower",))
        boots_charizard = self._set("charizard", item_id="heavydutyboots", moves=("flamethrower",))
        state = self._state(
            player_active=self._set("greattusk", moves=("rapidspin",)),
            player_team=(self._set("greattusk", moves=("rapidspin",)), charizard),
            opponent_active=self._set("blissey", moves=("seismictoss",)),
            player_stealth_rock=True,
        )

        with_rocks = evaluator.evaluate(state, charizard)
        with_boots = evaluator.evaluate(state, boots_charizard)

        self.assertLess(with_rocks.score, with_boots.score)
        self.assertTrue(any("Stealth Rock" in risk for risk in with_rocks.risks))

    def test_conservative_style_prefers_safer_action(self) -> None:
        safe = ActionSummary(
            action=BattleAction(ActionType.MOVE, move_id="safe"),
            average_utility=45,
            worst_case_utility=40,
            best_case_utility=50,
            reasons=(),
            risks=(),
        )
        risky = ActionSummary(
            action=BattleAction(ActionType.MOVE, move_id="risky"),
            average_utility=65,
            worst_case_utility=10,
            best_case_utility=100,
            reasons=(),
            risks=(),
        )

        self.assertGreater(
            _style_score(safe, DecisionStyle.CONSERVATIVE),
            _style_score(risky, DecisionStyle.CONSERVATIVE),
        )
        self.assertGreater(
            _style_score(risky, DecisionStyle.AGGRESSIVE),
            _style_score(safe, DecisionStyle.AGGRESSIVE),
        )

    def _state(
        self,
        player_active: PokemonSet,
        opponent_active: PokemonSet,
        player_team: tuple[PokemonSet, ...] | None = None,
        opponent_team: tuple[PokemonSet, ...] | None = None,
        player_hp: int = 300,
        opponent_hp: int = 300,
        trapped: bool = False,
        player_stealth_rock: bool = False,
    ) -> BattleState:
        return BattleState(
            generation=9,
            format_id="gen9ou",
            turn=1,
            player=BattleSideState(
                active=ActivePokemonState(player_active, current_hp=player_hp, trapped=trapped),
                team=player_team or (player_active,),
                stealth_rock=player_stealth_rock,
            ),
            opponent=BattleSideState(
                active=ActivePokemonState(opponent_active, current_hp=opponent_hp),
                team=opponent_team or (opponent_active,),
            ),
        )

    def _set(
        self,
        species_id: str,
        moves: tuple[str, ...],
        ability_id: str | None = None,
        item_id: str | None = None,
        nature: str | None = None,
        evs: EVSpread | None = None,
    ) -> PokemonSet:
        return PokemonSet(
            species_id=species_id,
            nickname=None,
            item_id=item_id,
            ability_id=ability_id,
            level=100,
            nature=nature,
            tera_type=None,
            moves=moves,
            evs=evs or EVSpread(),
        )


if __name__ == "__main__":
    unittest.main()
