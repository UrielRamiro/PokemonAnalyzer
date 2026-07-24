from __future__ import annotations

import shutil
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.replays.catalog import ReplayCatalog
from pokebrain.replays.extraction import PolicyExampleExtractionJob
from pokebrain.replays.models import RawReplay, ReplaySummary
from pokebrain.replays.public_events import MoveUsed, UnsupportedReplayEvent
from pokebrain.replays.public_models import ReplayReconstructionStatus
from pokebrain.replays.public_parser import PublicReplayParser
from pokebrain.replays.public_protocol import ReplayProtocolParser
from pokebrain.replays.storage import RawReplayStorage


class PublicReplayParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT_DIR / ".tmp_tests" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_protocol_parser_produces_typed_events_with_metadata(self) -> None:
        events = ReplayProtocolParser().parse("|turn|1\n|move|p1a: Garchomp|Earthquake|p2a: Dragapult\n|custom|x")

        self.assertIsInstance(events[1], MoveUsed)
        self.assertEqual(events[1].metadata.line_number, 2)
        self.assertEqual(events[1].metadata.raw_line, "|move|p1a: Garchomp|Earthquake|p2a: Dragapult")
        self.assertIsInstance(events[2], UnsupportedReplayEvent)

    def test_simple_attack_reconstructs_turn_start_states(self) -> None:
        parsed = PublicReplayParser().parse(replay_id="simple", format_id="gen9ou", raw_log=self._simple_log())

        turn_snapshots = [snapshot for snapshot in parsed.snapshots if snapshot.phase == "turn_start"]
        self.assertEqual(tuple(snapshot.turn for snapshot in turn_snapshots), (1,))
        self.assertEqual(len(parsed.decisions), 2)
        self.assertEqual(parsed.decisions[0].actual_action.action.move_id, "earthquake")
        self.assertIn(ReplayReconstructionStatus.PARTIAL_MISSING_LEGAL_ACTIONS, parsed.statuses)

    def test_switch_updates_active_pokemon_identity(self) -> None:
        log = self._simple_log(include_win=False) + "\n|switch|p1a: Great Tusk|Great Tusk|100/100"

        parsed = PublicReplayParser().parse(replay_id="switch", format_id="gen9ou", raw_log=log)
        p1 = next(side for side in parsed.snapshots[-1].state.sides if side.side == "p1")
        active = next(pokemon for pokemon in p1.pokemon if pokemon.active)

        self.assertEqual(active.species_id, "greattusk")

    def test_percentage_hp_is_not_converted_to_fake_exact_hp(self) -> None:
        log = self._simple_log(include_win=False) + "\n|-damage|p2a: Dragapult|83/100"

        parsed = PublicReplayParser().parse(replay_id="hp", format_id="gen9ou", raw_log=log)
        p2 = next(side for side in parsed.snapshots[-1].state.sides if side.side == "p2")
        dragapult = next(pokemon for pokemon in p2.pokemon if pokemon.species_id == "dragapult")

        self.assertIsNone(dragapult.hp_current)
        self.assertIsNone(dragapult.hp_max)
        self.assertAlmostEqual(dragapult.hp_fraction or 0, 0.83)

    def test_unrevealed_item_remains_unknown(self) -> None:
        parsed = PublicReplayParser().parse(replay_id="item", format_id="gen9ou", raw_log=self._simple_log())
        p1 = next(side for side in parsed.snapshots[-1].state.sides if side.side == "p1")
        garchomp = next(pokemon for pokemon in p1.pokemon if pokemon.species_id == "garchomp")

        self.assertIsNone(garchomp.revealed_item)

    def test_unknown_event_is_recorded_without_aborting(self) -> None:
        parsed = PublicReplayParser().parse(replay_id="unknown", format_id="gen9ou", raw_log=self._simple_log() + "\n|-mystery|p1a: Garchomp")

        self.assertIn(ReplayReconstructionStatus.UNSUPPORTED_PROTOCOL_EVENT, parsed.statuses)
        self.assertTrue(parsed.snapshots)

    def test_inconsistent_state_marks_replay_as_failed(self) -> None:
        log = "\n".join(
            (
                "|poke|p1|Garchomp, M|",
                "|switch|p1a: Garchomp|Garchomp, M|100/100",
                "|faint|p1a: Garchomp",
                "|switch|p1a: Garchomp|Garchomp, M|100/100",
            )
        )

        parsed = PublicReplayParser().parse(replay_id="bad", format_id="gen9ou", raw_log=log)

        self.assertIn(ReplayReconstructionStatus.STATE_INCONSISTENCY, parsed.statuses)

    def test_parser_is_deterministic(self) -> None:
        parser = PublicReplayParser()

        self.assertEqual(
            parser.parse(replay_id="det", format_id="gen9ou", raw_log=self._simple_log()),
            parser.parse(replay_id="det", format_id="gen9ou", raw_log=self._simple_log()),
        )

    def test_public_raw_replay_extracts_partial_examples(self) -> None:
        summary = ReplaySummary("public-1", "gen9ou", 1700, 1500, ("Alice", "Bob"))
        raw = RawReplay(
            replay_id=summary.replay_id,
            payload={"log": self._simple_log()},
            downloaded_at=datetime.now(timezone.utc),
            content_sha256="abc",
            raw_text="",
        )
        catalog = ReplayCatalog(self.root / "replays.db")
        storage = RawReplayStorage(self.root / "raw")
        catalog.save_success(summary, raw, storage.save(summary, raw))

        report = PolicyExampleExtractionJob(catalog=catalog, storage=storage).run(
            (summary.replay_id,),
            parser_version="public-parser-test",
            output_dir=self.root / "examples",
        )

        self.assertEqual(report.parsed, 1)
        self.assertEqual(report.examples, 2)
        self.assertEqual(catalog.get(summary.replay_id).parse_status, "partial")

    def _simple_log(self, include_win: bool = True) -> str:
        lines = [
                "|gen|9",
                "|tier|[Gen 9] OU",
                "|poke|p1|Garchomp, M|",
                "|poke|p1|Great Tusk|",
                "|poke|p2|Dragapult, F|",
                "|switch|p1a: Garchomp|Garchomp, M|100/100",
                "|switch|p2a: Dragapult|Dragapult, F|100/100",
                "|turn|1",
                "|move|p1a: Garchomp|Earthquake|p2a: Dragapult",
                "|move|p2a: Dragapult|Shadow Ball|p1a: Garchomp",
        ]
        if include_win:
            lines.append("|win|Alice")
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
