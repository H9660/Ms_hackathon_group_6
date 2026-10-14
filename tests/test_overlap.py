"""Overlap queries against the seeded Seminar Hall A booking (4 Aug 10:00-12:00)
and Conference Room C renovation block (4 Aug 09:00-18:00)."""

from datetime import datetime

import pytest

from cems import repository as repo
from cems.models import Event, Status


def at(hour, minute=0, day=4):
    return datetime(2026, 8, day, hour, minute)


@pytest.fixture
def hall(conn):
    return repo.get_venue_by_name(conn, "Seminar Hall A")


@pytest.mark.parametrize(
    "start, end, overlaps",
    [
        (at(9), at(11), True),          # overlaps the start
        (at(11), at(13), True),         # overlaps the end
        (at(10, 30), at(11, 30), True), # inside
        (at(9), at(13), True),          # encloses
        (at(10), at(12), True),         # identical
        (at(8), at(10), False),         # ends exactly when it starts
        (at(12), at(14), False),        # starts exactly when it ends
        (at(10, day=5), at(12, day=5), False),  # same time, other day
    ],
)
def test_event_overlap_boundaries(conn, hall, start, end, overlaps):
    found = repo.find_overlapping_events(conn, hall.id, start, end)
    assert bool(found) is overlaps


def test_other_venue_same_time_does_not_overlap(conn):
    auditorium = repo.get_venue_by_name(conn, "Main Auditorium")
    assert repo.find_overlapping_events(conn, auditorium.id, at(10), at(12)) == []


@pytest.mark.parametrize(
    "status, holds_venue",
    [
        (Status.PENDING, True),
        (Status.CONFIRMED, True),
        (Status.REJECTED, False),
        (Status.CANCELLED, False),
    ],
)
def test_only_active_statuses_hold_the_venue(conn, status, holds_venue):
    auditorium = repo.get_venue_by_name(conn, "Main Auditorium")
    repo.insert_event(
        conn, Event(None, "Fest", "Cultural", "Music Club", auditorium.id, at(14), at(16), 200, status)
    )
    found = repo.find_overlapping_events(conn, auditorium.id, at(15), at(17))
    assert bool(found) is holds_venue


def test_exclude_event_id_skips_that_event(conn, hall):
    seeded = repo.find_overlapping_events(conn, hall.id, at(10), at(12))[0]
    assert repo.find_overlapping_events(conn, hall.id, at(10), at(12), exclude_event_id=seeded.id) == []


@pytest.mark.parametrize(
    "start, end, overlaps",
    [
        (at(8), at(9, 30), True),
        (at(17), at(19), True),
        (at(7), at(9), False),     # ends when the block starts
        (at(18), at(20), False),   # starts when the block ends
    ],
)
def test_block_overlap_boundaries(conn, start, end, overlaps):
    room = repo.get_venue_by_name(conn, "Conference Room C")
    assert bool(repo.find_overlapping_blocks(conn, room.id, start, end)) is overlaps
