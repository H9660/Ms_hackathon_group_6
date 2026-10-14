from datetime import datetime

from cems.models import ACTIVE_STATUSES, EVENT_TYPES, Status, from_db, to_db


def test_datetime_round_trip_has_minute_precision():
    value = datetime(2026, 8, 4, 10, 30, 59)
    assert to_db(value) == "2026-08-04T10:30"
    assert from_db(to_db(value)) == datetime(2026, 8, 4, 10, 30)


def test_stored_datetimes_sort_chronologically():
    times = [datetime(2026, 12, 1, 9), datetime(2026, 8, 4, 18), datetime(2026, 8, 4, 9)]
    assert sorted(to_db(t) for t in times) == [to_db(t) for t in sorted(times)]


def test_only_pending_and_confirmed_hold_a_venue():
    assert set(ACTIVE_STATUSES) == {Status.PENDING, Status.CONFIRMED}
    assert Status.REJECTED not in ACTIVE_STATUSES
    assert Status.CANCELLED not in ACTIVE_STATUSES


def test_status_is_a_plain_string():
    assert Status.PENDING == "PENDING"
    assert Status("CONFIRMED") is Status.CONFIRMED


def test_event_types_are_unique():
    assert len(EVENT_TYPES) == len(set(EVENT_TYPES))
