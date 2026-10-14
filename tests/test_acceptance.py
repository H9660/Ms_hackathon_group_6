"""Acceptance scenarios S1-S12 from docs/TEST_SCENARIOS.md, driven through the UI.

Each test is one demo scenario, run in a single app session the way a
presenter would click through it, switching roles in the sidebar.
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cems import notifications as notify
from cems import repository as repo
from cems.db import get_conn
from cems.models import Status

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "acceptance.db"
    monkeypatch.setenv("CEMS_DB_PATH", str(path))
    return path


@pytest.fixture
def app(db_path):
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def db(db_path, fn):
    conn = get_conn(db_path)
    try:
        return fn(conn)
    finally:
        conn.close()


def vid(db_path, name):
    return db(db_path, lambda c: repo.get_venue_by_name(c, name).id)


def as_role(at, role, name=None):
    at.sidebar.radio(key="role").set_value(role).run()
    if name is not None:
        key = {"Requester": "actor_REQUESTER", "Reviewer": "actor_REVIEWER"}[role]
        at.sidebar.text_input(key=key).input(name).run()
    assert not at.exception


def request(at, db_path, venue, day, start, end, attendees, title="Hackathon Kickoff"):
    at.text_input(key="req_title").input(title)
    at.selectbox(key="req_venue").set_value(vid(db_path, venue))
    at.date_input(key="req_date").set_value(day)
    at.time_input(key="req_start").set_value(start)
    at.time_input(key="req_end").set_value(end)
    at.number_input(key="req_attendees").set_value(attendees)
    at.run()
    assert not at.exception


def errors(at):
    return " ".join(e.value for e in at.error)


def event_by_title(db_path, title):
    return db(db_path, lambda c: [e for e in repo.list_events(c) if e.title == title][0])


AUG4, AUG5 = date(2026, 8, 4), date(2026, 8, 5)


def test_s1_happy_path_end_to_end(app, db_path):
    request(app, db_path, "Main Auditorium", AUG5, time(14), time(16), 300)
    app.button(key="req_submit").click().run()
    event = event_by_title(db_path, "Hackathon Kickoff")
    assert event.status is Status.PENDING

    as_role(app, "Reviewer")
    app.button(key=f"approve_{event.id}").click().run()
    assert event_by_title(db_path, "Hackathon Kickoff").status is Status.CONFIRMED

    as_role(app, "Requester")
    assert any("was approved" in m.value for m in app.markdown)


def test_s2_overlap_is_blocked_before_submit(app, db_path):
    request(app, db_path, "Seminar Hall A", AUG4, time(11), time(13), 50)
    assert app.button(key="req_submit").disabled
    assert "already booked 04 Aug 2026 10:00–12:00" in errors(app)


def test_s3_renovation_is_blocked(app, db_path):
    request(app, db_path, "Conference Room C", AUG4, time(14), time(15), 20)
    assert app.button(key="req_submit").disabled
    assert "(Renovation)" in errors(app)


def test_s4_capacity_is_enforced(app, db_path):
    request(app, db_path, "Innovation Lab", AUG5, time(10), time(12), 80)
    assert app.button(key="req_submit").disabled
    assert "holds 60 people" in errors(app)


def test_s5_end_before_start(app, db_path):
    request(app, db_path, "Main Auditorium", AUG5, time(16), time(14), 100)
    assert app.button(key="req_submit").disabled
    assert "End time must be after the start time." in errors(app)


def test_s6_back_to_back_is_allowed(app, db_path):
    request(app, db_path, "Seminar Hall A", AUG4, time(12), time(14), 100)
    assert not app.button(key="req_submit").disabled


def test_s7_reject_releases_the_slot(app, db_path):
    request(app, db_path, "Main Auditorium", AUG5, time(14), time(16), 300)
    app.button(key="req_submit").click().run()
    event = event_by_title(db_path, "Hackathon Kickoff")

    as_role(app, "Reviewer")
    app.text_input(key=f"reason_{event.id}").input("Auditorium reserved for convocation prep").run()
    app.button(key=f"reject_{event.id}").click().run()

    as_role(app, "Requester", "Drama Club")
    request(app, db_path, "Main Auditorium", AUG5, time(14), time(16), 300, title="Annual Play")
    assert not app.button(key="req_submit").disabled


def test_s8_cancel_releases_the_slot(app, db_path):
    as_role(app, "Requester", "AI Club")
    app.button(key="cancel_1").click().run()
    assert db(db_path, lambda c: repo.get_event(c, 1)).status is Status.CANCELLED

    request(app, db_path, "Seminar Hall A", AUG4, time(10), time(12), 100, title="Replacement")
    assert not app.button(key="req_submit").disabled


def test_s9_block_over_booking_is_refused(app, db_path):
    as_role(app, "Facilities Manager")
    app.selectbox(key="blk_venue").set_value(vid(db_path, "Innovation Lab"))
    app.date_input(key="blk_start_date").set_value(date(2026, 8, 6))
    app.date_input(key="blk_end_date").set_value(date(2026, 8, 6))
    app.run()
    app.button(key="blk_submit").click().run()
    assert "Cannot block Innovation Lab" in errors(app)


def test_s10_removing_a_block_reopens_the_venue(app, db_path):
    as_role(app, "Facilities Manager")
    app.button(key="unblock_1").click().run()
    as_role(app, "Requester")
    request(app, db_path, "Conference Room C", AUG4, time(14), time(15), 20)
    assert not app.button(key="req_submit").disabled


def test_s11_schedule_shows_the_day(app, db_path):
    as_role(app, "Campus schedule")
    assert app.header[0].value == "Campus schedule"
    [day_table, _] = app.dataframe
    states = list(day_table.value["State"])
    assert states.count("CONFIRMED") == 1 and states.count("BLOCKED") == 1
    assert any("Free all day" in s.value and "Main Auditorium" in s.value for s in app.success)


def test_s12_reset_restores_initial_data(app, db_path):
    request(app, db_path, "Main Auditorium", AUG5, time(14), time(16), 300)
    app.button(key="req_submit").click().run()
    app.sidebar.button(key="reset_demo").click().run()
    assert not app.exception
    events = db(db_path, repo.list_events)
    assert len(events) == 2 and all(e.status is Status.CONFIRMED for e in events)
    assert db(db_path, lambda c: notify.list_for(c, notify.REVIEWER_INBOX)) == []


# ------------------------------------------------------- schedule details

def test_schedule_hides_released_requests_unless_asked(app, db_path):
    as_role(app, "Requester", "AI Club")
    app.button(key="cancel_1").click().run()
    as_role(app, "Campus schedule")
    states = list(app.dataframe[0].value["State"])
    assert "CANCELLED" not in states

    app.checkbox(key="sched_released").check().run()
    assert "CANCELLED" in list(app.dataframe[0].value["State"])


def test_schedule_empty_day(app):
    as_role(app, "Campus schedule")
    app.date_input(key="sched_date").set_value(date(2026, 9, 1)).run()
    assert not app.exception
    assert any("No bookings or blocks" in i.value for i in app.info)
