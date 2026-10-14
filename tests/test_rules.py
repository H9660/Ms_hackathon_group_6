from datetime import datetime, timedelta

import pytest

from cems import repository as repo
from cems.models import Event, Role, Status
from cems.rules import (
    MAX_DURATION,
    can_cancel,
    check_availability,
    format_window,
    validate_request,
)


def at(hour, minute=0, day=4):
    return datetime(2026, 8, day, hour, minute)


def venue_id(conn, name):
    return repo.get_venue_by_name(conn, name).id


def request(conn, **overrides):
    """validate_request with a valid default request (Main Auditorium, 5 Aug 14-16)."""
    args = dict(
        title="Tech Talk",
        organiser="Coding Club",
        event_type="Workshop",
        venue_id=venue_id(conn, "Main Auditorium"),
        start=at(14, day=5),
        end=at(16, day=5),
        attendees=300,
    )
    args.update(overrides)
    return validate_request(conn, **args)


# ---------------------------------------------------------------- happy path

def test_valid_request_passes(conn):
    assert request(conn) == []


# ------------------------------------------------------------ basic fields

@pytest.mark.parametrize("field", ["title", "organiser"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_required_text_fields(conn, field, value):
    reasons = request(conn, **{field: value})
    assert len(reasons) == 1
    assert "required" in reasons[0]


def test_unknown_event_type(conn):
    assert any("Event type" in r for r in request(conn, event_type="Party"))


@pytest.mark.parametrize("bad_id", [None, 999])
def test_unknown_venue(conn, bad_id):
    assert request(conn, venue_id=bad_id) == ["Please select an existing venue."]


# ------------------------------------------------------------- time window

def test_missing_times(conn):
    assert request(conn, start=None) == ["Start and end date-time are both required."]


@pytest.mark.parametrize("end", [at(14, day=5), at(13, day=5)])
def test_end_must_be_after_start(conn, end):
    assert request(conn, end=end) == ["End time must be after the start time."]


def test_exactly_max_duration_is_allowed(conn):
    start = at(8, day=5)
    assert request(conn, start=start, end=start + MAX_DURATION) == []


def test_longer_than_max_duration_is_rejected(conn):
    start = at(8, day=5)
    reasons = request(conn, start=start, end=start + MAX_DURATION + timedelta(minutes=1))
    assert reasons == ["An event can last at most 12 hours."]


# ---------------------------------------------------------------- capacity

def test_attendees_equal_to_capacity_is_allowed(conn):
    assert request(conn, attendees=500) == []


def test_capacity_exceeded_message_names_venue_and_numbers(conn):
    reasons = request(conn, venue_id=venue_id(conn, "Innovation Lab"), attendees=80)
    assert reasons == ["Innovation Lab holds 60 people; 80 expected attendees exceed its capacity."]


@pytest.mark.parametrize("attendees", [0, -5])
def test_attendees_must_be_positive(conn, attendees):
    assert request(conn, attendees=attendees) == ["Expected attendees must be at least 1."]


# ------------------------------------------------------- conflicts / blocks

def test_overlap_with_seeded_confirmed_event(conn):
    reasons = request(conn, venue_id=venue_id(conn, "Seminar Hall A"), start=at(11), end=at(13), attendees=50)
    assert reasons == [
        "Seminar Hall A is already booked 04 Aug 2026 10:00–12:00 "
        "for 'Intro to Machine Learning Workshop' (CONFIRMED)."
    ]


def test_back_to_back_with_seeded_event_is_allowed(conn):
    hall = venue_id(conn, "Seminar Hall A")
    assert request(conn, venue_id=hall, start=at(12), end=at(14), attendees=50) == []
    assert request(conn, venue_id=hall, start=at(8), end=at(10), attendees=50) == []


def test_renovation_block_is_reported_with_reason(conn):
    reasons = request(conn, venue_id=venue_id(conn, "Conference Room C"), start=at(10), end=at(11), attendees=20)
    assert reasons == ["Conference Room C is unavailable 04 Aug 2026 09:00–18:00 (Renovation)."]


def test_same_time_at_another_venue_is_allowed(conn):
    assert request(conn, start=at(10), end=at(12)) == []


def test_pending_request_holds_the_slot(conn):
    auditorium = venue_id(conn, "Main Auditorium")
    repo.insert_event(conn, Event(None, "Fest", "Cultural", "Music Club", auditorium,
                                  at(14, day=5), at(16, day=5), 200, Status.PENDING))
    reasons = request(conn)
    assert len(reasons) == 1
    assert "(PENDING)" in reasons[0]


@pytest.mark.parametrize("status", [Status.REJECTED, Status.CANCELLED])
def test_rejected_or_cancelled_release_the_slot(conn, status):
    auditorium = venue_id(conn, "Main Auditorium")
    repo.insert_event(conn, Event(None, "Fest", "Cultural", "Music Club", auditorium,
                                  at(14, day=5), at(16, day=5), 200, status))
    assert request(conn) == []


def test_check_availability_can_exclude_the_request_itself(conn):
    hall = repo.get_venue_by_name(conn, "Seminar Hall A")
    seeded = repo.list_events(conn, venue_id=hall.id)[0]
    assert check_availability(conn, hall, seeded.start, seeded.end) != []
    assert check_availability(conn, hall, seeded.start, seeded.end, exclude_event_id=seeded.id) == []


# ------------------------------------------------- multiple / dependent errors

def test_all_independent_problems_are_reported_together(conn):
    reasons = request(
        conn,
        title="",
        venue_id=venue_id(conn, "Seminar Hall A"),
        start=at(11),
        end=at(13),
        attendees=150,
    )
    assert len(reasons) == 3
    assert reasons[0] == "Event title is required."
    assert "holds 120 people" in reasons[1]
    assert "already booked" in reasons[2]


def test_availability_is_skipped_when_window_is_invalid(conn):
    reasons = request(conn, venue_id=venue_id(conn, "Seminar Hall A"), start=at(12), end=at(11), attendees=50)
    assert reasons == ["End time must be after the start time."]


# ---------------------------------------------------------------- formatting

def test_format_window_multi_day():
    assert format_window(at(22), at(2, day=5)) == "04 Aug 2026 22:00 – 05 Aug 2026 02:00"


# -------------------------------------------------------------- cancellation

@pytest.fixture
def confirmed(conn):
    return repo.list_events(conn, status=Status.CONFIRMED)[0]  # organiser: AI Club


def test_reviewer_can_cancel_any_confirmed_event(confirmed):
    assert can_cancel(confirmed, "Events Office", Role.REVIEWER) == []


@pytest.mark.parametrize("name", ["AI Club", "  ai club "])
def test_organiser_can_cancel_own_event(confirmed, name):
    assert can_cancel(confirmed, name, Role.REQUESTER) == []


def test_other_requester_cannot_cancel(confirmed):
    assert can_cancel(confirmed, "Drama Club", Role.REQUESTER) == [
        "Only the organiser (AI Club) or a Reviewer can cancel this event."
    ]


def test_facilities_manager_cannot_cancel(confirmed):
    assert can_cancel(confirmed, "AI Club", Role.FACILITIES) != []


@pytest.mark.parametrize("status", [Status.PENDING, Status.REJECTED, Status.CANCELLED])
def test_only_confirmed_events_can_be_cancelled(confirmed, status):
    confirmed.status = status
    assert can_cancel(confirmed, "Events Office", Role.REVIEWER) == [
        f"Only confirmed events can be cancelled (this event is {status.value})."
    ]
