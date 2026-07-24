from __future__ import annotations

import shutil
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from pokebrain.replays import (
    PolicyExampleExtractionJob,
    RawReplay,
    RawReplayStorage,
    ReplayCatalog,
    ReplayCollectionRequest,
    ReplayCollector,
    ReplayDownloadClient,
    ReplayDownloadError,
    ReplayHttpConfig,
    ReplayPaginationError,
    ReplayQualityConfig,
    ReplaySearchClient,
    ReplaySummary,
    anonymize_player,
)
from pokebrain.replays.serialization import content_hash


class ReplayDatasetCollectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT_DIR / ".tmp_tests" / self._testMethodName
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_search_paginates_using_last_upload_time(self) -> None:
        first = tuple(self._summary(index, 2000 - index) for index in range(51))
        second = (self._summary(100, 1900),)
        search = FakeSearchClient({None: first, first[49].upload_time: second})
        collector = self._collector(search)

        report = collector.collect(ReplayCollectionRequest(format_id="gen9ou", maximum_replays=51))

        self.assertEqual(search.before_values, [None, first[49].upload_time])
        self.assertEqual(report.downloaded, 51)

    def test_51st_result_is_not_processed_twice(self) -> None:
        first = tuple(self._summary(index, 2000 - index) for index in range(51))
        second = (first[50],)
        download = FakeDownloadClient()
        collector = self._collector(FakeSearchClient({None: first, first[49].upload_time: second}), download)

        collector.collect(ReplayCollectionRequest(format_id="gen9ou", maximum_replays=51))

        self.assertEqual(download.downloaded_ids.count(first[50].replay_id), 1)

    def test_pagination_cursor_must_advance(self) -> None:
        page = tuple(self._summary(index, 1000) for index in range(51))
        collector = self._collector(FakeSearchClient({None: page, 1000: page}))

        with self.assertRaises(ReplayPaginationError):
            collector.collect(ReplayCollectionRequest(format_id="gen9ou", maximum_replays=100))

    def test_existing_replay_is_not_downloaded_again(self) -> None:
        summary = self._summary(1, 1700)
        catalog = ReplayCatalog(self.root / "replays.db")
        storage = RawReplayStorage(self.root / "raw")
        raw = self._raw(summary.replay_id)
        catalog.save_success(summary, raw, storage.save(summary, raw))
        download = FakeDownloadClient()
        collector = ReplayCollector(
            search_client=FakeSearchClient({None: (summary,)}),
            download_client=download,
            catalog=catalog,
            storage=storage,
            quality_config=ReplayQualityConfig(minimum_turns=1),
        )

        report = collector.collect(ReplayCollectionRequest(format_id="gen9ou", maximum_replays=1))

        self.assertEqual(report.already_present, 1)
        self.assertEqual(download.downloaded_ids, [])

    def test_raw_payload_is_preserved_exactly(self) -> None:
        summary = self._summary(1, 1700)
        raw_text = '{"id":"gen9ou-1","log":"|turn|1\\n|win|p1"}'
        raw = RawReplay(
            replay_id=summary.replay_id,
            payload={"id": summary.replay_id, "log": "|turn|1\n|win|p1"},
            downloaded_at=datetime.now(timezone.utc),
            content_sha256=content_hash(raw_text),
            raw_text=raw_text,
        )
        storage = RawReplayStorage(self.root / "raw")

        path = storage.save(summary, raw)

        self.assertEqual(path.read_text(encoding="utf-8"), raw_text)

    def test_content_hash_is_deterministic(self) -> None:
        payload = '{"id":"gen9ou-1"}'

        self.assertEqual(content_hash(payload), content_hash(payload))
        self.assertNotEqual(content_hash(payload), content_hash('{"id":"gen9ou-2"}'))

    def test_timeout_is_retried_and_recorded(self) -> None:
        summary = self._summary(1, 1700)
        download = FakeDownloadClient(errors={summary.replay_id: ReplayDownloadError("timeout")})
        collector = self._collector(FakeSearchClient({None: (summary,)}), download)

        report = collector.collect(ReplayCollectionRequest(format_id="gen9ou", maximum_replays=1))

        self.assertEqual(report.failed, 1)
        catalogued = collector.catalog.get(summary.replay_id)
        self.assertIsNotNone(catalogued)
        self.assertEqual(catalogued.download_status, "failed")

    def test_download_client_retries_timeout(self) -> None:
        client = ReplayDownloadClient(
            base_url="https://example.test",
            config=ReplayHttpConfig(maximum_retries=1, retry_base_delay_seconds=0, requests_per_second=1000),
        )
        response = FakeHttpResponse('{"id":"gen9ou-1","log":"|turn|1\\n|win|p1"}')
        with patch("pokebrain.replays.http.urlopen", side_effect=(URLError("timeout"), response)) as opened:
            raw = client.download_json("gen9ou-1")

        self.assertEqual(raw.replay_id, "gen9ou-1")
        self.assertEqual(opened.call_count, 2)

    def test_invalid_replay_does_not_abort_collection(self) -> None:
        invalid = self._summary(1, 1700)
        valid = self._summary(2, 1600)
        download = FakeDownloadClient(payloads={invalid.replay_id: self._raw(invalid.replay_id, log="")})
        collector = self._collector(FakeSearchClient({None: (invalid, valid)}), download)

        report = collector.collect(ReplayCollectionRequest(format_id="gen9ou", maximum_replays=2))

        self.assertEqual(report.filtered, 1)
        self.assertEqual(report.downloaded, 1)

    def test_parser_can_reprocess_existing_raw_replay(self) -> None:
        summary = self._summary(1, 1700)
        catalog = ReplayCatalog(self.root / "replays.db")
        storage = RawReplayStorage(self.root / "raw")
        raw = RawReplay(
            replay_id=summary.replay_id,
            payload={"local_artifact_dir": str(ROOT_DIR / "runs" / "2026-07-20" / "policy-smoke-3")},
            downloaded_at=datetime.now(timezone.utc),
            content_sha256="abc",
            raw_text='{"local_artifact_dir":"runs/2026-07-20/policy-smoke-3"}',
        )
        catalog.save_success(summary, raw, storage.save(summary, raw))

        report = PolicyExampleExtractionJob(catalog=catalog, storage=storage).run(
            (summary.replay_id,),
            parser_version="test-parser-v1",
            output_dir=self.root / "examples",
        )

        self.assertEqual(report.parsed, 1)
        self.assertGreater(report.examples, 0)
        self.assertEqual(catalog.get(summary.replay_id).parse_status, "parsed")

    def test_anonymize_player_is_stable_and_salted(self) -> None:
        self.assertEqual(anonymize_player("Player", b"a"), anonymize_player("player", b"a"))
        self.assertNotEqual(anonymize_player("Player", b"a"), anonymize_player("Player", b"b"))

    def _collector(self, search, download=None) -> ReplayCollector:
        return ReplayCollector(
            search_client=search,
            download_client=download or FakeDownloadClient(),
            catalog=ReplayCatalog(self.root / "replays.db"),
            storage=RawReplayStorage(self.root / "raw"),
            quality_config=ReplayQualityConfig(minimum_turns=1),
        )

    def _summary(self, index: int, upload_time: int) -> ReplaySummary:
        return ReplaySummary(
            replay_id=f"gen9ou-{index}",
            format_id="gen9ou",
            upload_time=upload_time,
            rating=1500,
            players=("Alice", "Bob"),
        )

    def _raw(self, replay_id: str, log: str = "|turn|1\n|win|Alice") -> RawReplay:
        raw_text = f'{{"id":"{replay_id}","format":"gen9ou","p1":"Alice","p2":"Bob","log":"{log.replace(chr(10), chr(92) + "n")}"}}'
        return RawReplay(
            replay_id=replay_id,
            payload={"id": replay_id, "format": "gen9ou", "p1": "Alice", "p2": "Bob", "log": log},
            downloaded_at=datetime.now(timezone.utc),
            content_sha256=content_hash(raw_text),
            raw_text=raw_text,
        )


class FakeSearchClient(ReplaySearchClient):
    def __init__(self, pages) -> None:
        self.pages = pages
        self.before_values = []

    def search(self, *, format_id=None, user=None, before=None):
        self.before_values.append(before)
        return self.pages.get(before, ())


class FakeDownloadClient(ReplayDownloadClient):
    def __init__(self, payloads=None, errors=None) -> None:
        self.payloads = payloads or {}
        self.errors = errors or {}
        self.downloaded_ids = []

    def download_json(self, replay_id: str) -> RawReplay:
        self.downloaded_ids.append(replay_id)
        if replay_id in self.errors:
            raise self.errors[replay_id]
        return self.payloads.get(replay_id) or ReplayDatasetCollectorTest()._raw(replay_id)


class FakeHttpResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode("utf-8")


if __name__ == "__main__":
    unittest.main()
