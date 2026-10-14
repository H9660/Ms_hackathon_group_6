"""Venue availability management for the Facilities Manager.

Business condition 4: a venue may be unavailable because of maintenance,
renovation or another operational restriction. A block may not be placed
over an active booking (assumption A5), so a venue is never both committed
to an event and blocked at the same time.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from cems import repository as repo
from cems.db import transaction
from cems.models import VenueBlock
from cems.rules import format_window
from cems.services import BookingError

BLOCK_REASONS = ["Maintenance", "Renovation", "Other operational restriction"]


def add_block(
    conn: sqlite3.Connection,
    venue_id: int,
    start: datetime | None,
    end: datetime | None,
    reason: str,
) -> int:
    """Block a venue for [start, end). Returns the new block id.

    Unlike events, blocks may span several days (e.g. a week of renovation).
    Raises BookingError listing any active bookings in that period.
    """
    reason = (reason or "").strip()
    problems: list[str] = []
    if not reason:
        problems.append("A reason is required to block a venue.")
    if start is None or end is None:
        problems.append("Start and end date-time are both required.")
    elif end <= start:
        problems.append("End time must be after the start time.")
    if problems:
        raise BookingError(problems)

    with transaction(conn, immediate=True):
        venue = repo.get_venue(conn, venue_id)
        if venue is None:
            raise BookingError("Please select an existing venue.")
        clashes = repo.find_overlapping_events(conn, venue.id, start, end)
        if clashes:
            raise BookingError(
                [
                    f"Cannot block {venue.name} for {format_window(start, end)}: "
                    "cancel or reject these active bookings first.",
                    *(
                        f"#{e.id} '{e.title}' by {e.organiser}, "
                        f"{format_window(e.start, e.end)} ({e.status.value})"
                        for e in clashes
                    ),
                ]
            )
        return repo.insert_block(conn, VenueBlock(None, venue.id, start, end, reason))


def remove_block(conn: sqlite3.Connection, block_id: int) -> None:
    """Lift a block (e.g. maintenance finished early); the period becomes bookable."""
    with transaction(conn, immediate=True):
        try:
            repo.delete_block(conn, block_id)
        except repo.NotFoundError as err:
            raise BookingError(f"Venue block #{block_id} does not exist.") from err
