"""The stub's change feed (plan §13.3), backed by a small SQLite file.

The stub has no access to Boost's publish transactions, so it cannot write a
change row *in* the publish transaction the way real Boost must. Instead it
**polls** (``record``) and diffs the current snapshot against the last one it
saw, which is exactly what plan §4.5 describes: "Every 60 s it lists today's
Boost ... and compares versions with its last snapshot (a small SQLite file).
Each difference ... becomes a change row with an increasing ``seq``."

Commit-order safety (§13.3) is approximated by a **visibility lag**: a row is
never returned until ``visibility_lag_seconds`` after it was written, which is
longer than one poll cycle, so a slow reader never observes a gap. Retention is
approximated by **purging** rows older than ``retention_seconds`` and raising
``CursorExpiredError`` for a cursor at or before the purge watermark.
"""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime


class CursorExpiredError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ChangePage:
    items: list["ChangeRow"]
    next_cursor: str
    has_more: bool


@dataclass(frozen=True, slots=True)
class ChangeRow:
    seq: str
    entity_type: str
    id: str
    version: str
    change: str  # PUBLISHED | UNPUBLISHED
    published_at: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracked_entity (
    entity_type TEXT NOT NULL,
    id TEXT NOT NULL,
    version TEXT NOT NULL,
    PRIMARY KEY (entity_type, id)
);
CREATE TABLE IF NOT EXISTS change_log (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    id TEXT NOT NULL,
    version TEXT NOT NULL,
    change TEXT NOT NULL,
    published_at TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS purge_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    watermark INTEGER NOT NULL
);
"""


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


class ChangeTracker:
    """One SQLite connection, used synchronously (the stub's load is a single
    engine's 30 s poll plus occasional batch reads — not the hot path a real
    deployment needs async database access for)."""

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.execute("INSERT OR IGNORE INTO purge_state (id, watermark) VALUES (1, 0)")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def record(self, entity_type: str, snapshot: Mapping[str, str], now: float) -> int:
        """Diffs ``snapshot`` (id → version, every currently published entity of
        this type) against what was last seen, writing one row per difference.
        Returns how many rows were written."""
        previous = dict(
            self._conn.execute(
                "SELECT id, version FROM tracked_entity WHERE entity_type = ?", (entity_type,)
            ).fetchall()
        )
        written = 0
        for entity_id, version in snapshot.items():
            if previous.get(entity_id) != version:
                self._write(entity_type, entity_id, version, "PUBLISHED", now)
                written += 1
        for entity_id, version in previous.items():
            if entity_id not in snapshot:
                self._write(entity_type, entity_id, version, "UNPUBLISHED", now)
                written += 1
        self._conn.execute("DELETE FROM tracked_entity WHERE entity_type = ?", (entity_type,))
        self._conn.executemany(
            "INSERT INTO tracked_entity (entity_type, id, version) VALUES (?, ?, ?)",
            [(entity_type, entity_id, version) for entity_id, version in snapshot.items()],
        )
        self._conn.commit()
        return written

    def _write(
        self, entity_type: str, entity_id: str, version: str, change: str, now: float
    ) -> None:
        self._conn.execute(
            "INSERT INTO change_log (entity_type, id, version, change, published_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, version, change, _iso(now), now),
        )

    def purge(self, now: float, *, retention_seconds: float) -> None:
        cutoff = now - retention_seconds
        row = self._conn.execute(
            "SELECT MAX(seq) FROM change_log WHERE created_at < ?", (cutoff,)
        ).fetchone()
        purged_up_to = row[0]
        if purged_up_to is not None:
            self._conn.execute(
                "UPDATE purge_state SET watermark = MAX(watermark, ?) WHERE id = 1", (purged_up_to,)
            )
            self._conn.execute("DELETE FROM change_log WHERE created_at < ?", (cutoff,))
            self._conn.commit()

    def feed(
        self, after: int, limit: int, *, now: float, visibility_lag_seconds: float
    ) -> ChangePage:
        """Raises ``CursorExpiredError`` for a cursor at or before the purge watermark."""
        watermark = self._conn.execute("SELECT watermark FROM purge_state WHERE id = 1").fetchone()[
            0
        ]
        if after < watermark:
            raise CursorExpiredError
        visible_before = now - visibility_lag_seconds
        rows = self._conn.execute(
            "SELECT seq, entity_type, id, version, change, published_at FROM change_log "
            "WHERE seq > ? AND created_at <= ? ORDER BY seq LIMIT ?",
            (after, visible_before, limit + 1),
        ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [
            ChangeRow(str(seq), entity_type, entity_id, version, change, published_at)
            for seq, entity_type, entity_id, version, change, published_at in page
        ]
        next_cursor = items[-1].seq if items else str(after)
        return ChangePage(items=items, next_cursor=next_cursor, has_more=has_more)
