from __future__ import annotations

from dataclasses import dataclass

from pokebrain.replays.models import RawReplay, ReplaySummary


@dataclass(frozen=True, slots=True)
class ReplayQualityConfig:
    minimum_turns: int = 5
    require_finished_battle: bool = True
    require_rating: bool = False


def passes_summary_filters(
    summary: ReplaySummary,
    *,
    format_id: str,
    minimum_rating: int | None = None,
    maximum_rating: int | None = None,
    quality: ReplayQualityConfig | None = None,
) -> bool:
    config = quality or ReplayQualityConfig()
    if summary.format_id and summary.format_id != format_id:
        return False
    if config.require_rating and summary.rating is None:
        return False
    if minimum_rating is not None and (summary.rating is None or summary.rating < minimum_rating):
        return False
    if maximum_rating is not None and summary.rating is not None and summary.rating > maximum_rating:
        return False
    return True


def validate_raw_replay(raw: RawReplay, summary: ReplaySummary, quality: ReplayQualityConfig | None = None) -> tuple[bool, str | None]:
    config = quality or ReplayQualityConfig()
    payload = raw.payload
    if summary.format_id and str(payload.get("format") or summary.format_id) != summary.format_id:
        return False, "format_mismatch"
    players = tuple(value for value in (payload.get("p1"), payload.get("p2")) if value)
    if len(players) < 2 and len(summary.players) < 2:
        return False, "missing_players"
    log = str(payload.get("log") or payload.get("inputlog") or "")
    if not log.strip():
        return False, "empty_log"
    if _turn_count(log) < config.minimum_turns:
        return False, "too_few_turns"
    if config.require_finished_battle and not _finished(payload, log):
        return False, "unfinished_battle"
    return True, None


def _turn_count(log: str) -> int:
    return sum(1 for line in log.splitlines() if line.startswith("|turn|"))


def _finished(payload: dict[str, object], log: str) -> bool:
    if payload.get("winner"):
        return True
    return "|win|" in log or "|tie" in log
