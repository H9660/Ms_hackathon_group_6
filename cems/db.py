"""SQLite connection, schema and transaction helper.

Transaction policy
------------------
Connections run in autocommit mode (``isolation_level=None``): a single
statement outside a transaction commits immediately. Anything that performs
more than one write, or a read-then-write that must be atomic (e.g. conflict
check + insert), must be wrapped in :func:`transaction`. Repository functions
never commit on their own; the caller owns the transaction.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cems.models import Status

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "cems.db"

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in Status)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS venues (
    id        INTEGER PRIMARY KEY,
    name      TEXT    NOT NULL UNIQUE,
    type      TEXT    NOT NULL,
    capacity  INTEGER NOT NULL CHECK (capacity > 0)
);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY,
    title          TEXT    NOT NULL,
    event_type     TEXT    NOT NULL,
    organiser      TEXT    NOT NULL,
    venue_id       INTEGER NOT NULL REFERENCES venues(id),
    start_at       TEXT    NOT NULL,
    end_at         TEXT    NOT NULL,
    attendees      INTEGER NOT NULL CHECK (attendees > 0),
    status         TEXT    NOT NULL CHECK (status IN ({_STATUS_VALUES})),
    reject_reason  TEXT,
    created_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
    CHECK (end_at > start_at)
);
CREATE INDEX IF NOT EXISTS idx_events_venue_time ON events (venue_id, start_at, end_at);

CREATE TABLE IF NOT EXISTS venue_blocks (
    id        INTEGER PRIMARY KEY,
    venue_id  INTEGER NOT NULL REFERENCES venues(id),
    start_at  TEXT    NOT NULL,
    end_at    TEXT    NOT NULL,
    reason    TEXT    NOT NULL,
    CHECK (end_at > start_at)
);
CREATE INDEX IF NOT EXISTS idx_blocks_venue_time ON venue_blocks (venue_id, start_at, end_at);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY,
    event_id    INTEGER NOT NULL REFERENCES events(id),
    action      TEXT    NOT NULL,
    actor       TEXT    NOT NULL,
    detail      TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
);
"""

# Every data table, children before parents, so rows can be deleted without
# violating foreign keys. Add new tables here (e.g. notifications in Step 6).
TABLES_CHILD_FIRST: tuple[str, ...] = ("audit_log", "venue_blocks", "events", "venues")


def get_conn(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with foreign keys on and name-addressable rows.

    ``check_same_thread=False`` lets Streamlit share one cached connection
    across its script reruns.
    """
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes (idempotent)."""
    conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Run a block atomically: commit on success, roll back on any exception.

    ``immediate=True`` takes the write lock up front (``BEGIN IMMEDIATE``),
    which makes a check-then-write sequence safe against concurrent writers.
    If a transaction is already open, the block simply joins it.
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def clear_all(conn: sqlite3.Connection) -> None:
    """Delete every row from every table (schema is kept)."""
    with transaction(conn):
        for table in TABLES_CHILD_FIRST:
            conn.execute(f"DELETE FROM {table}")
