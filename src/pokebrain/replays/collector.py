from __future__ import annotations

from pokebrain.replays.catalog import ReplayCatalog
from pokebrain.replays.http import ReplayDownloadClient, ReplaySearchClient
from pokebrain.replays.models import (
    ReplayCollectionReport,
    ReplayCollectionRequest,
    ReplayDownloadError,
    ReplayNotFoundError,
    ReplayPaginationError,
    ReplaySummary,
)
from pokebrain.replays.quality import ReplayQualityConfig, passes_summary_filters, validate_raw_replay
from pokebrain.replays.storage import RawReplayStorage


class ReplayCollector:
    def __init__(
        self,
        *,
        search_client: ReplaySearchClient,
        download_client: ReplayDownloadClient,
        catalog: ReplayCatalog,
        storage: RawReplayStorage,
        quality_config: ReplayQualityConfig | None = None,
    ) -> None:
        self.search_client = search_client
        self.download_client = download_client
        self.catalog = catalog
        self.storage = storage
        self.quality_config = quality_config or ReplayQualityConfig()

    def collect(self, request: ReplayCollectionRequest) -> ReplayCollectionReport:
        report = ReplayCollectionReport(format_id=request.format_id)
        before = request.before
        previous_before: int | None = None

        while report.downloaded < request.maximum_replays:
            results = self.search_client.search(format_id=request.format_id, before=before)
            report.pages_requested += 1
            if not results:
                break
            usable_results = results[:50]
            report.discovered += len(usable_results)
            for summary in usable_results:
                if report.downloaded >= request.maximum_replays:
                    break
                self._collect_one(summary, request, report)
            if len(results) < 51:
                break
            previous_before, before = before, usable_results[-1].upload_time
            if before == previous_before:
                raise ReplayPaginationError("Replay pagination cursor did not advance.")

        return report

    def _collect_one(
        self,
        summary: ReplaySummary,
        request: ReplayCollectionRequest,
        report: ReplayCollectionReport,
    ) -> None:
        if not passes_summary_filters(
            summary,
            format_id=request.format_id,
            minimum_rating=request.minimum_rating,
            maximum_rating=request.maximum_rating,
            quality=self.quality_config,
        ):
            report.filtered += 1
            return
        if self.catalog.exists(summary.replay_id):
            report.already_present += 1
            return
        try:
            raw = self.download_client.download_json(summary.replay_id)
        except ReplayNotFoundError as exc:
            self.catalog.save_failure(summary, "not_found", str(exc))
            report.not_found += 1
            return
        except ReplayDownloadError as exc:
            self.catalog.save_failure(summary, "failed", str(exc))
            report.failed += 1
            return
        except Exception as exc:
            self.catalog.save_failure(summary, "failed", str(exc))
            report.failed += 1
            return

        valid, reason = validate_raw_replay(raw, summary, self.quality_config)
        if not valid:
            raw_path = self.storage.save(summary, raw)
            self.catalog.save_success(summary, raw, raw_path)
            self.catalog.mark_parse_failed(summary.replay_id, "quality-v1", reason or "quality_filter")
            report.filtered += 1
            return

        raw_path = self.storage.save(summary, raw)
        existing = self.catalog.get(summary.replay_id)
        if existing and existing.content_sha256 != raw.content_sha256:
            self.catalog.mark_content_changed(summary.replay_id, raw.content_sha256)
        self.catalog.save_success(summary, raw, raw_path)
        report.downloaded += 1
