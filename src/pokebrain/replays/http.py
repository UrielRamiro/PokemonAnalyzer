from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pokebrain.replays.models import RawReplay, ReplayDownloadError, ReplayNotFoundError, ReplaySummary
from pokebrain.replays.serialization import content_hash


@dataclass(frozen=True, slots=True)
class ReplayHttpConfig:
    request_timeout_seconds: float = 15.0
    requests_per_second: float = 2.0
    maximum_retries: int = 4
    retry_base_delay_seconds: float = 1.0


class ReplaySearchClient:
    def __init__(
        self,
        *,
        base_url: str = "https://replay.pokemonshowdown.com",
        config: ReplayHttpConfig | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config = config or ReplayHttpConfig()
        self._last_request_at = 0.0

    def search(
        self,
        *,
        format_id: str | None = None,
        user: str | None = None,
        before: int | None = None,
    ) -> tuple[ReplaySummary, ...]:
        query: dict[str, str] = {}
        if format_id:
            query["format"] = format_id
        if user:
            query["user"] = user
        if before is not None:
            query["before"] = str(before)
        suffix = f"?{urlencode(query)}" if query else ""
        payload = _request_json(f"{self.base_url}/search.json{suffix}", self.config, self._rate_limit)
        if not isinstance(payload, list):
            raise ReplayDownloadError("Replay search response was not a list.")
        return tuple(_summary_from_json(item) for item in payload if isinstance(item, dict))

    def _rate_limit(self) -> None:
        minimum_gap = 1.0 / max(0.1, self.config.requests_per_second)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum_gap:
            time.sleep(minimum_gap - elapsed)
        self._last_request_at = time.monotonic()


class ReplayDownloadClient:
    def __init__(
        self,
        *,
        base_url: str = "https://replay.pokemonshowdown.com",
        config: ReplayHttpConfig | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.config = config or ReplayHttpConfig()
        self._last_request_at = 0.0

    def download_json(self, replay_id: str) -> RawReplay:
        text = _request_text(f"{self.base_url}/{replay_id}.json", self.config, self._rate_limit)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ReplayDownloadError(f"Replay JSON is invalid: {exc}") from exc
        if not isinstance(payload, dict):
            raise ReplayDownloadError("Replay JSON response was not an object.")
        return RawReplay(
            replay_id=replay_id,
            payload=payload,
            downloaded_at=datetime.now(timezone.utc),
            content_sha256=content_hash(text),
            raw_text=text,
        )

    def _rate_limit(self) -> None:
        minimum_gap = 1.0 / max(0.1, self.config.requests_per_second)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < minimum_gap:
            time.sleep(minimum_gap - elapsed)
        self._last_request_at = time.monotonic()


def _request_json(url: str, config: ReplayHttpConfig, rate_limit) -> Any:
    return json.loads(_request_text(url, config, rate_limit))


def _request_text(url: str, config: ReplayHttpConfig, rate_limit) -> str:
    last_error: Exception | None = None
    for attempt in range(config.maximum_retries + 1):
        rate_limit()
        try:
            request = Request(url, headers={"User-Agent": "pokebrain-replay-collector/0.1"})
            with urlopen(request, timeout=config.request_timeout_seconds) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            if exc.code == 404:
                raise ReplayNotFoundError(f"Replay not found: {url}") from exc
            if exc.code == 429 or 500 <= exc.code <= 599:
                last_error = exc
                _sleep_backoff(config, attempt)
                continue
            raise ReplayDownloadError(f"Replay HTTP error {exc.code}: {url}") from exc
        except (TimeoutError, URLError) as exc:
            last_error = exc
            _sleep_backoff(config, attempt)
    raise ReplayDownloadError(f"Replay request failed after retries: {last_error}") from last_error


def _sleep_backoff(config: ReplayHttpConfig, attempt: int) -> None:
    if attempt >= config.maximum_retries:
        return
    time.sleep(config.retry_base_delay_seconds * (2**attempt))


def _summary_from_json(data: dict[str, Any]) -> ReplaySummary:
    replay_id = str(data.get("id") or data.get("replayid") or data.get("replay_id") or "")
    format_id = str(data.get("format") or data.get("formatid") or data.get("format_id") or "")
    upload_time = int(data.get("uploadtime") or data.get("upload_time") or data.get("uploadTime") or 0)
    rating = _optional_int(data.get("rating"))
    players = tuple(str(value) for value in (data.get("players") or ()) if value)
    if not players:
        players = tuple(str(data.get(key)) for key in ("p1", "p2") if data.get(key))
    return ReplaySummary(replay_id=replay_id, format_id=format_id, upload_time=upload_time, rating=rating, players=players)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
