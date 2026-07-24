from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    replay_id: str
    format_id: str
    upload_time: int
    rating: int | None
    players: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RawReplay:
    replay_id: str
    payload: dict[str, object]
    downloaded_at: datetime
    content_sha256: str
    raw_text: str = ""


@dataclass(frozen=True, slots=True)
class ReplayCollectionRequest:
    format_id: str
    maximum_replays: int
    before: int | None = None
    minimum_rating: int | None = None
    maximum_rating: int | None = None


@dataclass(slots=True)
class ReplayCollectionReport:
    format_id: str
    discovered: int = 0
    downloaded: int = 0
    already_present: int = 0
    filtered: int = 0
    not_found: int = 0
    failed: int = 0
    pages_requested: int = 0


@dataclass(frozen=True, slots=True)
class CatalogReplay:
    replay_id: str
    format_id: str
    upload_time: int
    rating: int | None
    players: tuple[str, ...]
    raw_path: Path
    content_sha256: str
    download_status: str
    parse_status: str
    downloaded_at: str
    parsed_at: str | None
    parser_version: str | None
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class PolicyExampleMetadata:
    replay_id: str
    turn_number: int
    player_side: str
    format_id: str
    upload_time: int
    rating_bucket: str | None
    parser_version: str
    feature_version: str
    belief_model_version: str


class ReplayCollectionError(Exception):
    pass


class ReplayPaginationError(ReplayCollectionError):
    pass


class ReplayNotFoundError(ReplayCollectionError):
    pass


class ReplayDownloadError(ReplayCollectionError):
    pass


def rating_bucket(rating: int | None) -> str | None:
    if rating is None:
        return None
    if rating < 1300:
        return "low"
    if rating < 1700:
        return "medium"
    return "high"


JsonDict = dict[str, Any]
