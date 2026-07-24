from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from pokebrain.replays.models import CatalogReplay, RawReplay, ReplaySummary


class ReplayCatalog:
    def __init__(self, database_path: Path | str = "data/database/replays.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def exists(self, replay_id: str) -> bool:
        return self.get(replay_id) is not None

    def get(self, replay_id: str) -> CatalogReplay | None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM replay_catalog WHERE replay_id = ?", (replay_id,)).fetchone()
            return _hydrate(row) if row else None

    def list_by_status(
        self,
        *,
        format_id: str,
        parse_status: str = "pending",
        limit: int | None = None,
    ) -> tuple[CatalogReplay, ...]:
        sql = "SELECT * FROM replay_catalog WHERE format_id = ? AND parse_status = ? ORDER BY upload_time"
        params: list[object] = [format_id, parse_status]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
            return tuple(_hydrate(row) for row in rows)

    def list_all(self, *, format_id: str | None = None) -> tuple[CatalogReplay, ...]:
        sql = "SELECT * FROM replay_catalog"
        params: list[object] = []
        if format_id is not None:
            sql += " WHERE format_id = ?"
            params.append(format_id)
        sql += " ORDER BY upload_time, replay_id"
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()
            return tuple(_hydrate(row) for row in rows)

    def save_success(self, summary: ReplaySummary, raw: RawReplay, raw_path: Path) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO replay_catalog (
                        replay_id, format_id, upload_time, rating, player_1, player_2,
                        raw_path, content_sha256, download_status, parse_status,
                        downloaded_at, parsed_at, parser_version, failure_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'downloaded', 'pending', ?, NULL, NULL, NULL)
                    ON CONFLICT(replay_id) DO UPDATE SET
                        content_sha256 = excluded.content_sha256,
                        raw_path = excluded.raw_path,
                        download_status = excluded.download_status,
                        downloaded_at = excluded.downloaded_at,
                        failure_reason = NULL
                    """,
                    (
                        summary.replay_id,
                        summary.format_id,
                        summary.upload_time,
                        summary.rating,
                        summary.players[0] if len(summary.players) > 0 else None,
                        summary.players[1] if len(summary.players) > 1 else None,
                        str(raw_path),
                        raw.content_sha256,
                        raw.downloaded_at.isoformat(),
                    ),
                )

    def save_failure(self, summary: ReplaySummary, status: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO replay_catalog (
                        replay_id, format_id, upload_time, rating, player_1, player_2,
                        raw_path, content_sha256, download_status, parse_status,
                        downloaded_at, parsed_at, parser_version, failure_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, '', '', ?, 'failed', ?, NULL, NULL, ?)
                    ON CONFLICT(replay_id) DO UPDATE SET
                        download_status = excluded.download_status,
                        parse_status = excluded.parse_status,
                        failure_reason = excluded.failure_reason
                    """,
                    (
                        summary.replay_id,
                        summary.format_id,
                        summary.upload_time,
                        summary.rating,
                        summary.players[0] if len(summary.players) > 0 else None,
                        summary.players[1] if len(summary.players) > 1 else None,
                        status,
                        now,
                        reason,
                    ),
                )

    def mark_content_changed(self, replay_id: str, new_sha256: str) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE replay_catalog
                    SET download_status = 'content_changed', failure_reason = ?
                    WHERE replay_id = ?
                    """,
                    (f"Content hash changed to {new_sha256}.", replay_id),
                )

    def mark_parsed(self, replay_id: str, parser_version: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE replay_catalog
                    SET parse_status = 'parsed', parsed_at = ?, parser_version = ?, failure_reason = NULL
                    WHERE replay_id = ?
                    """,
                    (now, parser_version, replay_id),
                )

    def mark_parse_failed(self, replay_id: str, parser_version: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE replay_catalog
                    SET parse_status = 'failed', parsed_at = ?, parser_version = ?, failure_reason = ?
                    WHERE replay_id = ?
                    """,
                    (now, parser_version, reason, replay_id),
                )

    def mark_parse_status(self, replay_id: str, parser_version: str, status: str, reason: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE replay_catalog
                    SET parse_status = ?, parsed_at = ?, parser_version = ?, failure_reason = ?
                    WHERE replay_id = ?
                    """,
                    (status, now, parser_version, reason, replay_id),
                )

    def _initialize(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS replay_catalog (
                        replay_id TEXT PRIMARY KEY,
                        format_id TEXT NOT NULL,
                        upload_time INTEGER NOT NULL,
                        rating INTEGER,
                        player_1 TEXT,
                        player_2 TEXT,
                        raw_path TEXT NOT NULL,
                        content_sha256 TEXT NOT NULL,
                        download_status TEXT NOT NULL,
                        parse_status TEXT NOT NULL DEFAULT 'pending',
                        downloaded_at TEXT NOT NULL,
                        parsed_at TEXT,
                        parser_version TEXT,
                        failure_reason TEXT
                    )
                    """
                )


def _hydrate(row: sqlite3.Row) -> CatalogReplay:
    players = tuple(player for player in (row["player_1"], row["player_2"]) if player)
    return CatalogReplay(
        replay_id=row["replay_id"],
        format_id=row["format_id"],
        upload_time=row["upload_time"],
        rating=row["rating"],
        players=players,
        raw_path=Path(row["raw_path"]),
        content_sha256=row["content_sha256"],
        download_status=row["download_status"],
        parse_status=row["parse_status"],
        downloaded_at=row["downloaded_at"],
        parsed_at=row["parsed_at"],
        parser_version=row["parser_version"],
        failure_reason=row["failure_reason"],
    )
