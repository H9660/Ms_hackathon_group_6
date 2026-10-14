"""In-app notifications: store, lifecycle hooks and atomicity."""

from datetime import datetime

import pytest

from cems import notifications as notify
from cems import repository as repo
from cems import services
from cems.models import Role
from cems.seed import reset_db
from cems.services import BookingError

REVIEWER = notify.REVIEWER_INBOX


def at(hour, day=5):
    return datetime(2026, 8, day, hour)


@pytest.fixture
def auditorium(conn):
    return repo.get_venue_by_name(conn, "Main Auditorium").id


def submit(conn, venue_id, organiser="Coding Club"):
    return services.submit_request(
        conn, "Tech Talk", "Workshop", organiser, venue_id, at(14), at(16), 300
    )


def messages(conn, recipient):
    return [n.message for n in notify.list_for(conn, recipient)]


# -------------------------------------------------------------------- store

def test_seed_has_no_notifications(conn):
    assert notify.list_for(conn, REVIEWER) == []
    assert notify.unread_count(conn, "AI Club") == 0


def test_store_is_newest_first_and_case_insensitive(conn):
    notify.notify(conn, "Coding Club", "first")
    notify.notify(conn, " coding club ", "second")
    assert messages(conn, "CODING CLUB") == ["second", "first"]
    assert notify.unread_count(conn, "Coding Club") == 2
    assert notify.list_for(conn, "Drama Club") == []


def test_mark_read_and_mark_all_read(conn):
    first = notify.notify(conn, "Coding Club", "first")
    notify.notify(conn, "Coding Club", "second")
    notify.notify(conn, "Drama Club", "other")

    notify.mark_read(conn, first)
    assert notify.unread_count(conn, "Coding Club") == 1
    assert [n.message for n in notify.list_for(conn, "Coding Club", unread_only=True)] == ["second"]

    assert notify.mark_all_read(conn, "Coding Club") == 1
    assert notify.unread_count(conn, "Coding Club") == 0
    assert notify.unread_count(conn, "Drama Club") == 1  # others untouched


# -------------------------------------------------------- lifecycle hooks

def test_submit_notifies_reviewers(conn, auditorium):
    event_id = submit(conn, auditorium)
    [n] = notify.list_for(conn, REVIEWER)
    assert n.event_id == event_id
    assert n.message == (
        f"New request #{event_id} 'Tech Talk' at Main Auditorium, 05 Aug 2026 14:00–16:00 "
        "from Coding Club is waiting for review."
    )
    assert notify.list_for(conn, "Coding Club") == []


def test_approve_notifies_organiser(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.approve_request(conn, event_id, "Events Office")
    [n] = notify.list_for(conn, "Coding Club")
    assert "was approved by Events Office" in n.message
    assert "CONFIRMED" in n.message
    assert n.event_id == event_id


def test_reject_notifies_organiser_with_reason(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.reject_request(conn, event_id, "Events Office", "Clashes with exams")
    [n] = notify.list_for(conn, "Coding Club")
    assert "rejected by Events Office: Clashes with exams" in n.message
    assert "submit a new request" in n.message


def test_reviewer_cancel_notifies_organiser(conn):
    services.cancel_event(conn, 1, "Events Office", Role.REVIEWER)  # seeded, AI Club
    [n] = notify.list_for(conn, "AI Club")
    assert "was cancelled by Events Office" in n.message
    assert notify.list_for(conn, REVIEWER) == []


def test_organiser_cancel_notifies_reviewers(conn):
    services.cancel_event(conn, 1, "AI Club", Role.REQUESTER)
    [n] = notify.list_for(conn, REVIEWER)
    assert n.message.startswith("AI Club cancelled #1 'Intro to Machine Learning Workshop'")
    assert "free again" in n.message
    assert notify.list_for(conn, "AI Club") == []


def test_full_lifecycle_message_trail(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.approve_request(conn, event_id, "Events Office")
    services.cancel_event(conn, event_id, "Coding Club", Role.REQUESTER)
    assert len(notify.list_for(conn, REVIEWER)) == 2  # new request + cancellation
    assert len(notify.list_for(conn, "Coding Club")) == 1  # approval


# --------------------------------------------- no notification on failure

def test_failed_submit_sends_nothing(conn):
    hall = repo.get_venue_by_name(conn, "Seminar Hall A").id
    with pytest.raises(BookingError):
        services.submit_request(
            conn, "Clash", "Workshop", "Coding Club", hall, at(11, day=4), at(13, day=4), 50
        )
    assert notify.list_for(conn, REVIEWER) == []


def test_refused_transitions_send_nothing(conn, auditorium):
    event_id = submit(conn, auditorium)
    services.reject_request(conn, event_id, "Events Office", "No")
    before = len(notify.list_for(conn, "Coding Club"))
    with pytest.raises(BookingError):
        services.approve_request(conn, event_id, "Events Office")
    with pytest.raises(BookingError):
        services.cancel_event(conn, 1, "Drama Club", Role.REQUESTER)
    assert len(notify.list_for(conn, "Coding Club")) == before
    assert notify.list_for(conn, "AI Club") == []


def test_notification_rolls_back_with_its_transition(conn, auditorium, monkeypatch):
    event_id = submit(conn, auditorium)

    def broken(*args, **kwargs):
        raise RuntimeError("notification store down")

    monkeypatch.setattr(notify, "notify", broken)
    with pytest.raises(RuntimeError):
        services.approve_request(conn, event_id, "Events Office")
    # The approval itself was rolled back: no half-done transition.
    assert repo.get_event(conn, event_id).status.value == "PENDING"


def test_reset_clears_notifications(conn, auditorium):
    submit(conn, auditorium)
    reset_db(conn)
    assert notify.list_for(conn, REVIEWER) == []
