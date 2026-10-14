"""Initial campus data from the problem statement.

Run ``python -m cems.seed`` to create and seed the local database file, or
``python -m cems.seed --reset`` to wipe it back to the initial state.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import replace
from datetime import datetime

from cems import repository as repo
from cems.db import DEFAULT_DB_PATH, clear_all, get_conn, init_db, transaction
from cems.models import Event, Status, Venue, VenueBlock

SEED_ACTOR = "system"

SEED_VENUES: list[Venue] = [
    Venue(None, "Seminar Hall A", "Seminar Hall", 120),
    Venue(None, "Main Auditorium", "Auditorium", 500),
    Venue(None, "Conference Room C", "Conference Room", 40),
    Venue(None, "Central Amphitheatre", "Open Venue", 300),
    Venue(None, "Innovation Lab", "Computer Lab", 60),
]

# (venue name, event) -- venue_id is resolved at insert time.
SEED_EVENTS: list[tuple[str, Event]] = [
    (
        "Seminar Hall A",
        Event(None, "Intro to Machine Learning Workshop", "Workshop", "AI Club", 0,
              datetime(2026, 8, 4, 10, 0), datetime(2026, 8, 4, 12, 0), 100, Status.CONFIRMED),
    ),
    (
        "Innovation Lab",
        Event(None, "Placement Coding Assessment", "Placement", "Placement Cell", 0,
              datetime(2026, 8, 6, 14, 0), datetime(2026, 8, 6, 17, 0), 55, Status.CONFIRMED),
    ),
]

SEED_BLOCKS: list[tuple[str, VenueBlock]] = [
    (
        "Conference Room C",
        VenueBlock(None, 0, datetime(2026, 8, 4, 9, 0), datetime(2026, 8, 4, 18, 0), "Renovation"),
    ),
]


def _venue_id(conn: sqlite3.Connection, name: str) -> int:
    venue = repo.get_venue_by_name(conn, name)
    if venue is None or venue.id is None:
        raise repo.NotFoundError(f"Seed venue '{name}' missing")
    return venue.id


def seed(conn: sqlite3.Connection) -> bool:
    """Load the initial data if the database is empty.

    Returns True if data was inserted, False if it was already present.
    """
    if repo.list_venues(conn):
        return False
    with transaction(conn):
        for venue in SEED_VENUES:
            repo.insert_venue(conn, venue)
        for venue_name, event in SEED_EVENTS:
            event_id = repo.insert_event(conn, replace(event, venue_id=_venue_id(conn, venue_name)))
            repo.log_action(conn, event_id, "SEEDED", SEED_ACTOR, "Initial campus data")
        for venue_name, block in SEED_BLOCKS:
            repo.insert_block(conn, replace(block, venue_id=_venue_id(conn, venue_name)))
    return True


def reset_db(conn: sqlite3.Connection) -> None:
    """Wipe all data and reload the initial campus data (for demos)."""
    with transaction(conn):
        clear_all(conn)
        seed(conn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and seed the CEMS database.")
    parser.add_argument("--reset", action="store_true", help="wipe existing data first")
    args = parser.parse_args()

    conn = get_conn()
    try:
        init_db(conn)
        if args.reset:
            reset_db(conn)
            print(f"Reset and seeded {DEFAULT_DB_PATH}")
        elif seed(conn):
            print(f"Seeded {DEFAULT_DB_PATH}")
        else:
            print(f"{DEFAULT_DB_PATH} already contains data; nothing to do")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
