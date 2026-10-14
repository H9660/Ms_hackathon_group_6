"""The seeded database must match the 'Initial Campus Data' table in the brief."""

from datetime import datetime

from cems import repository as repo
from cems.db import get_conn, init_db
from cems.models import Event, Status
from cems.seed import reset_db, seed


def test_five_venues_with_brief_capacities(conn):
    venues = {v.name: (v.type, v.capacity) for v in repo.list_venues(conn)}
    assert venues == {
        "Seminar Hall A": ("Seminar Hall", 120),
        "Main Auditorium": ("Auditorium", 500),
        "Conference Room C": ("Conference Room", 40),
        "Central Amphitheatre": ("Open Venue", 300),
        "Innovation Lab": ("Computer Lab", 60),
    }


def _confirmed_slot(conn, venue_name):
    venue = repo.get_venue_by_name(conn, venue_name)
    events = repo.list_events(conn, venue_id=venue.id)
    assert len(events) == 1
    event = events[0]
    assert event.status is Status.CONFIRMED
    assert event.attendees <= venue.capacity
    return event.start, event.end


def test_seminar_hall_a_confirmed_on_4_aug_10_to_12(conn):
    assert _confirmed_slot(conn, "Seminar Hall A") == (
        datetime(2026, 8, 4, 10, 0),
        datetime(2026, 8, 4, 12, 0),
    )


def test_innovation_lab_confirmed_on_6_aug_14_to_17(conn):
    assert _confirmed_slot(conn, "Innovation Lab") == (
        datetime(2026, 8, 6, 14, 0),
        datetime(2026, 8, 6, 17, 0),
    )


def test_conference_room_c_blocked_for_renovation(conn):
    venue = repo.get_venue_by_name(conn, "Conference Room C")
    blocks = repo.list_blocks(conn)
    assert len(blocks) == 1
    block = blocks[0]
    assert block.venue_id == venue.id
    assert (block.start, block.end) == (datetime(2026, 8, 4, 9, 0), datetime(2026, 8, 4, 18, 0))
    assert block.reason == "Renovation"


def test_available_venues_have_no_bookings_or_blocks(conn):
    for name in ("Main Auditorium", "Central Amphitheatre"):
        venue = repo.get_venue_by_name(conn, name)
        assert repo.list_events(conn, venue_id=venue.id) == []
        assert repo.list_blocks(conn, venue_id=venue.id) == []


def test_seeded_events_have_audit_entry(conn):
    for event in repo.list_events(conn):
        history = repo.get_history(conn, event.id)
        assert [h.action for h in history] == ["SEEDED"]


def test_seed_is_idempotent(conn):
    assert seed(conn) is False
    assert len(repo.list_venues(conn)) == 5
    assert len(repo.list_events(conn)) == 2
    assert len(repo.list_blocks(conn)) == 1


def test_reset_restores_initial_state(conn):
    venue = repo.get_venue_by_name(conn, "Main Auditorium")
    repo.insert_event(
        conn,
        Event(None, "Extra", "Cultural", "Drama Club", venue.id,
              datetime(2026, 8, 5, 10), datetime(2026, 8, 5, 12), 200, Status.PENDING),
    )
    assert len(repo.list_events(conn)) == 3

    reset_db(conn)

    assert len(repo.list_venues(conn)) == 5
    assert len(repo.list_events(conn)) == 2
    assert len(repo.list_blocks(conn)) == 1
    assert not conn.in_transaction


def test_seed_persists_to_a_database_file(tmp_path):
    path = tmp_path / "cems.db"
    first = get_conn(path)
    init_db(first)
    seed(first)
    first.close()

    second = get_conn(path)
    try:
        assert len(repo.list_venues(second)) == 5
    finally:
        second.close()
