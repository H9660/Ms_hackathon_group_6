"""Request lifecycle: submit -> review -> confirm/reject -> cancel."""

from datetime import datetime

import pytest

from cems import repository as repo
from cems import services
from cems.models import Event, Role, Status, VenueBlock
from cems.services import BookingError


def at(hour, day=5):
    return datetime(2026, 8, day, hour)


@pytest.fixture
def auditorium(conn):
    return repo.get_venue_by_name(conn, "Main Auditorium").id


def submit(conn, venue_id, organiser="Coding Club", start=None, end=None, attendees=300):
    return services.submit_request(
        conn,
        title="Tech Talk",
        event_type="Workshop",
        organiser=organiser,
        venue_id=venue_id,
        start=start or at(14),
        end=end or at(16),
        attendees=attendees,
    )


def status_of(conn, event_id):
    return repo.get_event(conn, event_id).status


def actions(conn, event_id):
    return [h.action for h in repo.get_history(conn, event_id)]


# -------------------------------------------------------------- end to end

def test_submit_approve_cancel_then_slot_is_bookable_again(conn, auditorium):
    event_id = submit(conn, auditorium)
    assert status_of(conn, event_id) is Status.PENDING

    services.approve_request(conn, event_id, "Events Office")
    assert status_of(conn, event_id) is Status.CONFIRMED

    services.cancel_event(conn, event_id, "Coding Club", Role.REQUESTER)
    assert status_of(conn, event_id) is Status.CANCELLED
    assert actions(conn, event_id) == ["SUBMITTED", "APPROVED", "CANCELLED"]

    # Condition 8: cancelling released the venue.
    again = submit(conn, auditorium, organiser="Drama Club")
    assert status_of(conn, again) is Status.PENDING


def test_reject_closes_request_and_releases_slot(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.reject_request(conn, event_id, "Events Office", "  Clashes with exams  ")

    event = repo.get_event(conn, event_id)
    assert event.status is Status.REJECTED
    assert event.reject_reason == "Clashes with exams"
    assert repo.get_history(conn, event_id)[-1].detail == "Clashes with exams"

    # Condition 6: another organiser can now book the same period.
    other = submit(conn, auditorium, organiser="Drama Club")
    assert status_of(conn, other) is Status.PENDING


def test_reviewer_can_cancel_someone_elses_event(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.approve_request(conn, event_id, "Events Office")
    services.cancel_event(conn, event_id, "Events Office", Role.REVIEWER)
    assert status_of(conn, event_id) is Status.CANCELLED


# -------------------------------------------------------------- submission

def test_submit_stores_trimmed_fields_and_audit_detail(conn, auditorium):
    event_id = services.submit_request(
        conn, "  Tech Talk ", "Workshop", " Coding Club ", auditorium, at(14), at(16), 300
    )
    event = repo.get_event(conn, event_id)
    assert (event.title, event.organiser) == ("Tech Talk", "Coding Club")
    entry = repo.get_history(conn, event_id)[0]
    assert (entry.action, entry.actor) == ("SUBMITTED", "Coding Club")
    assert "Main Auditorium" in entry.detail


def test_pending_request_blocks_second_submission(conn, auditorium):
    submit(conn, auditorium)
    with pytest.raises(BookingError) as err:
        submit(conn, auditorium, organiser="Drama Club", start=at(15), end=at(17))
    assert "(PENDING)" in err.value.reasons[0]
    assert len(repo.list_events(conn, venue_id=auditorium)) == 1


def test_invalid_submission_writes_nothing(conn):
    hall = repo.get_venue_by_name(conn, "Seminar Hall A").id
    before = len(repo.list_events(conn))
    with pytest.raises(BookingError) as err:
        submit(conn, hall, start=at(11, day=4), end=at(13, day=4), attendees=150)
    assert len(err.value.reasons) == 2  # capacity + overlap
    assert len(repo.list_events(conn)) == before
    assert not conn.in_transaction


def test_failure_after_insert_rolls_everything_back(conn, auditorium, monkeypatch):
    def broken_log(*args, **kwargs):
        raise RuntimeError("audit log unavailable")

    monkeypatch.setattr(repo, "log_action", broken_log)
    with pytest.raises(RuntimeError):
        submit(conn, auditorium)
    assert repo.list_events(conn, venue_id=auditorium) == []
    assert not conn.in_transaction


def test_booking_error_accepts_single_reason():
    err = BookingError("nope")
    assert err.reasons == ["nope"]
    assert str(err) == "nope"


# ---------------------------------------------------------------- approval

def test_approve_rechecks_availability(conn, auditorium):
    event_id = submit(conn, auditorium)
    # Simulate a block that bypassed the normal checks (e.g. direct data fix).
    repo.insert_block(conn, VenueBlock(None, auditorium, at(15), at(18), "Electrical maintenance"))

    with pytest.raises(BookingError) as err:
        services.approve_request(conn, event_id, "Events Office")
    assert err.value.reasons[0] == f"Cannot approve request #{event_id}:"
    assert "Electrical maintenance" in err.value.reasons[1]
    assert status_of(conn, event_id) is Status.PENDING


def test_approve_does_not_conflict_with_itself(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.approve_request(conn, event_id, "Events Office")
    assert status_of(conn, event_id) is Status.CONFIRMED


def test_approve_unknown_event(conn):
    with pytest.raises(BookingError, match="does not exist"):
        services.approve_request(conn, 999, "Events Office")


# ----------------------------------------------------- invalid transitions

@pytest.mark.parametrize("first", ["approve", "reject"])
@pytest.mark.parametrize("second", ["approve", "reject"])
def test_only_pending_requests_can_be_reviewed(conn, auditorium, first, second):
    event_id = submit(conn, auditorium)
    review = {
        "approve": lambda: services.approve_request(conn, event_id, "Events Office"),
        "reject": lambda: services.reject_request(conn, event_id, "Events Office", "No"),
    }
    review[first]()
    status_after_first = status_of(conn, event_id)

    with pytest.raises(BookingError, match="Only PENDING requests"):
        review[second]()
    assert status_of(conn, event_id) is status_after_first


def test_cannot_cancel_pending_request(conn, auditorium):
    event_id = submit(conn, auditorium)
    with pytest.raises(BookingError, match="Only confirmed events"):
        services.cancel_event(conn, event_id, "Coding Club", Role.REQUESTER)


def test_cannot_cancel_twice(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.approve_request(conn, event_id, "Events Office")
    services.cancel_event(conn, event_id, "Coding Club", Role.REQUESTER)
    with pytest.raises(BookingError, match="Only confirmed events"):
        services.cancel_event(conn, event_id, "Coding Club", Role.REQUESTER)


def test_other_requester_cannot_cancel(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.approve_request(conn, event_id, "Events Office")
    with pytest.raises(BookingError, match="Only the organiser"):
        services.cancel_event(conn, event_id, "Drama Club", Role.REQUESTER)
    assert status_of(conn, event_id) is Status.CONFIRMED


def test_cancel_seeded_confirmed_event_releases_seminar_hall(conn):
    hall = repo.get_venue_by_name(conn, "Seminar Hall A").id
    seeded = repo.list_events(conn, venue_id=hall)[0]
    services.cancel_event(conn, seeded.id, "AI Club", Role.REQUESTER)
    new_id = submit(conn, hall, start=seeded.start, end=seeded.end, attendees=100)
    assert status_of(conn, new_id) is Status.PENDING


# ---------------------------------------------------------- required inputs

@pytest.mark.parametrize("reason", ["", "   ", None])
def test_reject_requires_reason(conn, auditorium, reason):
    event_id = submit(conn, auditorium)
    with pytest.raises(BookingError, match="reason is required"):
        services.reject_request(conn, event_id, "Events Office", reason)
    assert status_of(conn, event_id) is Status.PENDING


@pytest.mark.parametrize(
    "call",
    [
        lambda c, i: services.approve_request(c, i, " "),
        lambda c, i: services.reject_request(c, i, "", "No"),
        lambda c, i: services.cancel_event(c, i, None, Role.REVIEWER),
    ],
)
def test_actor_name_is_required(conn, auditorium, call):
    event_id = submit(conn, auditorium)
    with pytest.raises(BookingError, match="name is required"):
        call(conn, event_id)
