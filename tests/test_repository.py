from datetime import datetime

import pytest

from cems import repository as repo
from cems.models import Event, Status, VenueBlock


def _venue_id(conn, name="Main Auditorium"):
    return repo.get_venue_by_name(conn, name).id


def _event(venue_id, organiser="Drama Club", status=Status.PENDING, day=5):
    return Event(None, "Annual Play", "Cultural", organiser, venue_id,
                 datetime(2026, 8, day, 14), datetime(2026, 8, day, 16), 300, status)


def test_get_venue_returns_none_for_unknown_id(conn):
    assert repo.get_venue(conn, 999) is None
    assert repo.get_venue_by_name(conn, "Nowhere") is None


def test_list_venues_is_sorted_by_name(conn):
    names = [v.name for v in repo.list_venues(conn)]
    assert names == sorted(names)


def test_insert_and_get_event_round_trip(conn):
    original = _event(_venue_id(conn))
    event_id = repo.insert_event(conn, original)
    stored = repo.get_event(conn, event_id)
    assert stored.id == event_id
    assert stored.status is Status.PENDING
    assert (stored.title, stored.start, stored.end, stored.attendees) == (
        original.title, original.start, original.end, original.attendees,
    )


def test_get_event_returns_none_for_unknown_id(conn):
    assert repo.get_event(conn, 999) is None


def test_list_events_filters(conn):
    venue_id = _venue_id(conn)
    repo.insert_event(conn, _event(venue_id, organiser="Drama Club", day=5))
    repo.insert_event(conn, _event(venue_id, organiser="Music Club", day=7))

    assert len(repo.list_events(conn)) == 4
    assert len(repo.list_events(conn, status=Status.CONFIRMED)) == 2
    assert [e.organiser for e in repo.list_events(conn, status=Status.PENDING)] == [
        "Drama Club", "Music Club",
    ]
    assert len(repo.list_events(conn, organiser="Music Club")) == 1
    assert len(repo.list_events(conn, venue_id=venue_id, organiser="Drama Club")) == 1


def test_list_events_is_ordered_by_start(conn):
    venue_id = _venue_id(conn)
    repo.insert_event(conn, _event(venue_id, day=20))
    repo.insert_event(conn, _event(venue_id, day=1))
    starts = [e.start for e in repo.list_events(conn)]
    assert starts == sorted(starts)


def test_update_status_sets_reason(conn):
    event_id = repo.insert_event(conn, _event(_venue_id(conn)))
    repo.update_status(conn, event_id, Status.REJECTED, reason="Clashes with exams")
    stored = repo.get_event(conn, event_id)
    assert stored.status is Status.REJECTED
    assert stored.reject_reason == "Clashes with exams"


def test_update_status_unknown_event_raises(conn):
    with pytest.raises(repo.NotFoundError):
        repo.update_status(conn, 999, Status.CONFIRMED)


def test_insert_and_list_blocks_by_venue(conn):
    venue_id = _venue_id(conn, "Innovation Lab")
    block_id = repo.insert_block(
        conn, VenueBlock(None, venue_id, datetime(2026, 8, 10, 9), datetime(2026, 8, 10, 13), "Maintenance")
    )
    blocks = repo.list_blocks(conn, venue_id=venue_id)
    assert [b.id for b in blocks] == [block_id]
    assert blocks[0].reason == "Maintenance"
    assert len(repo.list_blocks(conn)) == 2


def test_audit_history_is_oldest_first(conn):
    event_id = repo.insert_event(conn, _event(_venue_id(conn)))
    repo.log_action(conn, event_id, "SUBMITTED", "Drama Club")
    repo.log_action(conn, event_id, "APPROVED", "Reviewer", "Looks good")
    history = repo.get_history(conn, event_id)
    assert [(h.action, h.actor, h.detail) for h in history] == [
        ("SUBMITTED", "Drama Club", ""),
        ("APPROVED", "Reviewer", "Looks good"),
    ]
    assert repo.get_history(conn, 999) == []
