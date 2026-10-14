"""Venue blocks (business condition 4, assumption A5)."""

from datetime import datetime

import pytest

from cems import repository as repo
from cems import services, venue_service
from cems.models import Role, Status
from cems.services import BookingError


def at(hour, day=5):
    return datetime(2026, 8, day, hour)


@pytest.fixture
def auditorium(conn):
    return repo.get_venue_by_name(conn, "Main Auditorium").id


def submit(conn, venue_id, start=None, end=None):
    return services.submit_request(
        conn, "Tech Talk", "Workshop", "Coding Club", venue_id, start or at(14), end or at(16), 100
    )


def test_block_on_free_slot(conn, auditorium):
    block_id = venue_service.add_block(conn, auditorium, at(9), at(12), "  Maintenance  ")
    [block] = repo.list_blocks(conn, venue_id=auditorium)
    assert (block.id, block.reason) == (block_id, "Maintenance")


def test_multi_day_block_is_allowed(conn, auditorium):
    venue_service.add_block(conn, auditorium, at(8, day=10), at(18, day=14), "Renovation")
    assert len(repo.list_blocks(conn, venue_id=auditorium)) == 1


def test_block_over_confirmed_event_is_refused(conn):
    hall = repo.get_venue_by_name(conn, "Seminar Hall A").id
    with pytest.raises(BookingError) as err:
        venue_service.add_block(conn, hall, at(9, day=4), at(11, day=4), "Maintenance")
    assert err.value.reasons[0].startswith("Cannot block Seminar Hall A")
    assert "Intro to Machine Learning Workshop" in err.value.reasons[1]
    assert "(CONFIRMED)" in err.value.reasons[1]
    assert repo.list_blocks(conn, venue_id=hall) == []


def test_block_over_pending_request_is_refused(conn, auditorium):
    submit(conn, auditorium)
    with pytest.raises(BookingError) as err:
        venue_service.add_block(conn, auditorium, at(15), at(20), "Maintenance")
    assert "(PENDING)" in err.value.reasons[1]


def test_block_adjacent_to_booking_is_allowed(conn):
    hall = repo.get_venue_by_name(conn, "Seminar Hall A").id
    venue_service.add_block(conn, hall, at(12, day=4), at(18, day=4), "Maintenance")
    venue_service.add_block(conn, hall, at(7, day=4), at(10, day=4), "Maintenance")
    assert len(repo.list_blocks(conn, venue_id=hall)) == 2


@pytest.mark.parametrize("finish", ["reject", "cancel"])
def test_released_slot_can_be_blocked(conn, auditorium, finish):
    event_id = submit(conn, auditorium)
    if finish == "reject":
        services.reject_request(conn, event_id, "Events Office", "Venue needed for maintenance")
    else:
        services.approve_request(conn, event_id, "Events Office")
        services.cancel_event(conn, event_id, "Events Office", Role.REVIEWER)
    venue_service.add_block(conn, auditorium, at(14), at(16), "Maintenance")
    assert repo.get_event(conn, event_id).status in (Status.REJECTED, Status.CANCELLED)


def test_request_inside_block_is_refused(conn, auditorium):
    venue_service.add_block(conn, auditorium, at(9), at(18), "Electrical maintenance")
    with pytest.raises(BookingError) as err:
        submit(conn, auditorium)
    assert err.value.reasons == [
        "Main Auditorium is unavailable 05 Aug 2026 09:00–18:00 (Electrical maintenance)."
    ]


def test_removing_block_makes_venue_bookable(conn):
    room = repo.get_venue_by_name(conn, "Conference Room C").id
    [renovation] = repo.list_blocks(conn, venue_id=room)
    venue_service.remove_block(conn, renovation.id)
    event_id = services.submit_request(
        conn, "Board Meeting", "Club", "Robotics Club", room, at(10, day=4), at(11, day=4), 20
    )
    assert repo.get_event(conn, event_id).status is Status.PENDING


def test_remove_unknown_block(conn):
    with pytest.raises(BookingError, match="does not exist"):
        venue_service.remove_block(conn, 999)


@pytest.mark.parametrize(
    "start, end, reason, message",
    [
        (at(9), at(12), "  ", "A reason is required to block a venue."),
        (at(12), at(12), "Maintenance", "End time must be after the start time."),
        (None, at(12), "Maintenance", "Start and end date-time are both required."),
    ],
)
def test_block_input_validation(conn, auditorium, start, end, reason, message):
    with pytest.raises(BookingError) as err:
        venue_service.add_block(conn, auditorium, start, end, reason)
    assert err.value.reasons == [message]


def test_block_unknown_venue(conn):
    with pytest.raises(BookingError, match="existing venue"):
        venue_service.add_block(conn, 999, at(9), at(12), "Maintenance")
