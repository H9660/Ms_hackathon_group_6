"""Data access: translates between SQLite rows and domain dataclasses.

Functions here contain no business rules and never commit; wrap multi-step
writes in :func:`cems.db.transaction`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from cems.models import (
    ACTIVE_STATUSES,
    AuditEntry,
    Event,
    Status,
    Venue,
    VenueBlock,
    from_db,
    to_db,
)


class NotFoundError(LookupError):
    """Raised when a referenced record does not exist."""


# --------------------------------------------------------------------------
# Row mappers
# --------------------------------------------------------------------------

def _to_venue(row: sqlite3.Row) -> Venue:
    return Venue(id=row["id"], name=row["name"], type=row["type"], capacity=row["capacity"])


def _to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        title=row["title"],
        event_type=row["event_type"],
        organiser=row["organiser"],
        venue_id=row["venue_id"],
        start=from_db(row["start_at"]),
        end=from_db(row["end_at"]),
        attendees=row["attendees"],
        status=Status(row["status"]),
        reject_reason=row["reject_reason"],
    )


def _to_block(row: sqlite3.Row) -> VenueBlock:
    return VenueBlock(
        id=row["id"],
        venue_id=row["venue_id"],
        start=from_db(row["start_at"]),
        end=from_db(row["end_at"]),
        reason=row["reason"],
    )


def _to_audit(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        id=row["id"],
        event_id=row["event_id"],
        action=row["action"],
        actor=row["actor"],
        detail=row["detail"],
        created_at=row["created_at"],
    )


# --------------------------------------------------------------------------
# Venues
# --------------------------------------------------------------------------

def list_venues(conn: sqlite3.Connection) -> list[Venue]:
    rows = conn.execute("SELECT * FROM venues ORDER BY name").fetchall()
    return [_to_venue(r) for r in rows]


def get_venue(conn: sqlite3.Connection, venue_id: int) -> Venue | None:
    row = conn.execute("SELECT * FROM venues WHERE id = ?", (venue_id,)).fetchone()
    return _to_venue(row) if row else None


def get_venue_by_name(conn: sqlite3.Connection, name: str) -> Venue | None:
    row = conn.execute("SELECT * FROM venues WHERE name = ?", (name,)).fetchone()
    return _to_venue(row) if row else None


def insert_venue(conn: sqlite3.Connection, venue: Venue) -> int:
    cur = conn.execute(
        "INSERT INTO venues (name, type, capacity) VALUES (?, ?, ?)",
        (venue.name, venue.type, venue.capacity),
    )
    return cur.lastrowid


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

def list_events(
    conn: sqlite3.Connection,
    status: Status | None = None,
    organiser: str | None = None,
    venue_id: int | None = None,
) -> list[Event]:
    """List events ordered by start time, optionally filtered."""
    clauses: list[str] = []
    params: list[object] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(Status(status).value)
    if organiser is not None:
        clauses.append("organiser = ?")
        params.append(organiser)
    if venue_id is not None:
        clauses.append("venue_id = ?")
        params.append(venue_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM events {where} ORDER BY start_at, id", params).fetchall()
    return [_to_event(r) for r in rows]


def find_overlapping_events(
    conn: sqlite3.Connection,
    venue_id: int,
    start: datetime,
    end: datetime,
    exclude_event_id: int | None = None,
) -> list[Event]:
    """Active (PENDING/CONFIRMED) events at a venue that overlap [start, end).

    Intervals are half-open, so back-to-back bookings do not overlap.
    ``exclude_event_id`` skips one event, e.g. a pending request being
    re-checked during approval must not conflict with itself.
    """
    placeholders = ", ".join("?" for _ in ACTIVE_STATUSES)
    sql = (
        "SELECT * FROM events "
        f"WHERE venue_id = ? AND status IN ({placeholders}) "
        "AND start_at < ? AND ? < end_at"
    )
    params: list[object] = [venue_id, *(s.value for s in ACTIVE_STATUSES), to_db(end), to_db(start)]
    if exclude_event_id is not None:
        sql += " AND id != ?"
        params.append(exclude_event_id)
    rows = conn.execute(sql + " ORDER BY start_at, id", params).fetchall()
    return [_to_event(r) for r in rows]


def get_event(conn: sqlite3.Connection, event_id: int) -> Event | None:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _to_event(row) if row else None


def insert_event(conn: sqlite3.Connection, event: Event) -> int:
    cur = conn.execute(
        """
        INSERT INTO events
            (title, event_type, organiser, venue_id, start_at, end_at,
             attendees, status, reject_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.title,
            event.event_type,
            event.organiser,
            event.venue_id,
            to_db(event.start),
            to_db(event.end),
            event.attendees,
            Status(event.status).value,
            event.reject_reason,
        ),
    )
    return cur.lastrowid


def update_status(
    conn: sqlite3.Connection,
    event_id: int,
    status: Status,
    reason: str | None = None,
) -> None:
    """Set an event's status (and optional rejection reason).

    No transition rules are applied here; that is the services layer's job.
    """
    cur = conn.execute(
        "UPDATE events SET status = ?, reject_reason = ? WHERE id = ?",
        (Status(status).value, reason, event_id),
    )
    if cur.rowcount == 0:
        raise NotFoundError(f"Event {event_id} does not exist")


# --------------------------------------------------------------------------
# Venue blocks
# --------------------------------------------------------------------------

def list_blocks(conn: sqlite3.Connection, venue_id: int | None = None) -> list[VenueBlock]:
    if venue_id is None:
        rows = conn.execute("SELECT * FROM venue_blocks ORDER BY start_at, id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM venue_blocks WHERE venue_id = ? ORDER BY start_at, id", (venue_id,)
        ).fetchall()
    return [_to_block(r) for r in rows]


def find_overlapping_blocks(
    conn: sqlite3.Connection,
    venue_id: int,
    start: datetime,
    end: datetime,
) -> list[VenueBlock]:
    """Blocks at a venue that overlap [start, end) (half-open intervals)."""
    rows = conn.execute(
        "SELECT * FROM venue_blocks WHERE venue_id = ? AND start_at < ? AND ? < end_at "
        "ORDER BY start_at, id",
        (venue_id, to_db(end), to_db(start)),
    ).fetchall()
    return [_to_block(r) for r in rows]


def insert_block(conn: sqlite3.Connection, block: VenueBlock) -> int:
    cur = conn.execute(
        "INSERT INTO venue_blocks (venue_id, start_at, end_at, reason) VALUES (?, ?, ?, ?)",
        (block.venue_id, to_db(block.start), to_db(block.end), block.reason),
    )
    return cur.lastrowid


def delete_block(conn: sqlite3.Connection, block_id: int) -> None:
    cur = conn.execute("DELETE FROM venue_blocks WHERE id = ?", (block_id,))
    if cur.rowcount == 0:
        raise NotFoundError(f"Venue block {block_id} does not exist")


# --------------------------------------------------------------------------
# Audit log
# --------------------------------------------------------------------------

def log_action(
    conn: sqlite3.Connection,
    event_id: int,
    action: str,
    actor: str,
    detail: str = "",
) -> None:
    conn.execute(
        "INSERT INTO audit_log (event_id, action, actor, detail) VALUES (?, ?, ?, ?)",
        (event_id, action, actor, detail),
    )


def get_history(conn: sqlite3.Connection, event_id: int) -> list[AuditEntry]:
    """Audit entries for an event, oldest first."""
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE event_id = ? ORDER BY id", (event_id,)
    ).fetchall()
    return [_to_audit(r) for r in rows]
