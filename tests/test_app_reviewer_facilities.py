"""UI tests for the Reviewer and Facilities Manager pages and the demo reset."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cems import repository as repo
from cems import services
from cems.db import get_conn, init_db
from cems.models import Status
from cems.seed import seed

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("CEMS_DB_PATH", str(path))
    conn = get_conn(path)
    init_db(conn)
    seed(conn)
    conn.close()
    return path


def with_db(db_path, fn):
    conn = get_conn(db_path)
    try:
        return fn(conn)
    finally:
        conn.close()


def submit_pending(db_path) -> int:
    def _submit(conn):
        venue = repo.get_venue_by_name(conn, "Main Auditorium")
        return services.submit_request(
            conn, "Tech Talk", "Workshop", "Coding Club", venue.id,
            datetime(2026, 8, 5, 14), datetime(2026, 8, 5, 16), 300,
        )
    return with_db(db_path, _submit)


def event(db_path, event_id):
    return with_db(db_path, lambda c: repo.get_event(c, event_id))


def open_as(role) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    at.sidebar.radio(key="role").set_value(role).run()
    assert not at.exception
    return at


# ------------------------------------------------------------------ reviewer

def test_reviewer_with_empty_queue(db_path):
    at = open_as("Reviewer")
    assert at.header[0].value == "Reviewer"
    assert any("No requests are waiting" in i.value for i in at.info)


def test_reviewer_approves_pending_request(db_path):
    event_id = submit_pending(db_path)
    at = open_as("Reviewer")

    at.button(key=f"approve_{event_id}").click().run()

    assert not at.exception
    assert any("approved and is now CONFIRMED" in s.value for s in at.success)
    assert event(db_path, event_id).status is Status.CONFIRMED
    history = with_db(db_path, lambda c: repo.get_history(c, event_id))
    assert [(h.action, h.actor) for h in history][-1] == ("APPROVED", "Events Office")


def test_reject_needs_a_reason(db_path):
    event_id = submit_pending(db_path)
    at = open_as("Reviewer")
    assert at.button(key=f"reject_{event_id}").disabled

    at.text_input(key=f"reason_{event_id}").input("Clashes with exams").run()
    at.button(key=f"reject_{event_id}").click().run()

    assert not at.exception
    rejected = event(db_path, event_id)
    assert rejected.status is Status.REJECTED
    assert rejected.reject_reason == "Clashes with exams"


def test_reviewer_cancels_confirmed_event(db_path):
    at = open_as("Reviewer")
    at.button(key="rev_cancel_1").click().run()  # seeded Seminar Hall A event
    assert not at.exception
    assert event(db_path, 1).status is Status.CANCELLED


def test_conflicting_pending_request_cannot_be_approved(db_path):
    event_id = submit_pending(db_path)
    # A block added behind the system's back (bypassing add_block).
    with_db(db_path, lambda c: c.execute(
        "INSERT INTO venue_blocks (venue_id, start_at, end_at, reason) "
        "SELECT id, '2026-08-05T15:00', '2026-08-05T17:00', 'Emergency repair' "
        "FROM venues WHERE name = 'Main Auditorium'"
    ))
    at = open_as("Reviewer")
    assert at.button(key=f"approve_{event_id}").disabled
    assert any("Emergency repair" in w.value for w in at.warning)


# ---------------------------------------------------------------- facilities

def _fill_block(at, db_path, venue, day, start, end):
    vid = with_db(db_path, lambda c: repo.get_venue_by_name(c, venue).id)
    at.selectbox(key="blk_venue").set_value(vid)
    at.date_input(key="blk_start_date").set_value(day)
    at.date_input(key="blk_end_date").set_value(day)
    at.time_input(key="blk_start_time").set_value(start)
    at.time_input(key="blk_end_time").set_value(end)
    at.text_input(key="blk_notes").input("Projector replacement")
    at.run()
    return vid


def test_facilities_lists_seeded_renovation(db_path):
    at = open_as("Facilities Manager")
    assert any("Conference Room C" in m.value and "Renovation" in m.value for m in at.markdown)


def test_facilities_blocks_a_free_slot(db_path):
    at = open_as("Facilities Manager")
    vid = _fill_block(at, db_path, "Main Auditorium", date(2026, 8, 5), time(9), time(12))
    at.button(key="blk_submit").click().run()

    assert not at.exception
    assert any("Block #" in s.value for s in at.success)
    [block] = with_db(db_path, lambda c: repo.list_blocks(c, venue_id=vid))
    assert block.reason == "Maintenance: Projector replacement"


def test_facilities_cannot_block_over_booking(db_path):
    at = open_as("Facilities Manager")
    _fill_block(at, db_path, "Seminar Hall A", date(2026, 8, 4), time(9), time(11))
    assert any("active booking(s)" in w.value for w in at.warning)

    at.button(key="blk_submit").click().run()

    assert any("Cannot block Seminar Hall A" in e.value for e in at.error)
    assert len(with_db(db_path, repo.list_blocks)) == 1  # only the seeded block


def test_facilities_removes_block(db_path):
    at = open_as("Facilities Manager")
    at.button(key="unblock_1").click().run()
    assert not at.exception
    assert with_db(db_path, repo.list_blocks) == []
    assert any("No venues are blocked" in i.value for i in at.info)


# --------------------------------------------------------------------- reset

def test_reset_demo_data_restores_seed(db_path):
    submit_pending(db_path)
    at = open_as("Reviewer")
    at.sidebar.button(key="reset_demo").click().run()

    assert not at.exception
    assert any("Demo data reset" in s.value for s in at.success)
    events = with_db(db_path, repo.list_events)
    assert [e.status for e in events] == [Status.CONFIRMED, Status.CONFIRMED]
