"""UI tests for the requester page using Streamlit's headless AppTest runner."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cems import repository as repo
from cems.db import get_conn
from cems.models import Status

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("CEMS_DB_PATH", str(path))
    return path


@pytest.fixture
def app(db_path):
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def venue_id(db_path, name):
    conn = get_conn(db_path)
    try:
        return repo.get_venue_by_name(conn, name).id
    finally:
        conn.close()


def events(db_path):
    conn = get_conn(db_path)
    try:
        return repo.list_events(conn)
    finally:
        conn.close()


def fill(at, db_path, venue, day, start, end, attendees, title="Tech Talk"):
    at.text_input(key="req_title").input(title)
    at.selectbox(key="req_venue").set_value(venue_id(db_path, venue))
    at.date_input(key="req_date").set_value(day)
    at.time_input(key="req_start").set_value(start)
    at.time_input(key="req_end").set_value(end)
    at.number_input(key="req_attendees").set_value(attendees)
    at.run()
    assert not at.exception


def submit_button(at):
    return at.button(key="req_submit")


def test_app_starts_on_requester_page(app):
    assert app.sidebar.radio(key="role").value == "Requester"
    assert app.header[0].value == "Requester"
    assert app.sidebar.text_input(key="actor_REQUESTER").value == "Coding Club"


def test_empty_title_blocks_submission(app):
    assert submit_button(app).disabled
    assert any("Event title is required." in e.value for e in app.error)


def test_conflict_is_shown_live_and_submit_disabled(app, db_path):
    fill(app, db_path, "Seminar Hall A", date(2026, 8, 4), time(11), time(13), 50)
    assert submit_button(app).disabled
    assert any("Seminar Hall A is already booked" in e.value for e in app.error)


def test_renovation_block_is_shown_live(app, db_path):
    fill(app, db_path, "Conference Room C", date(2026, 8, 4), time(10), time(11), 20)
    assert submit_button(app).disabled
    assert any("(Renovation)" in e.value for e in app.error)


def test_capacity_is_shown_live(app, db_path):
    fill(app, db_path, "Innovation Lab", date(2026, 8, 7), time(10), time(12), 80)
    assert submit_button(app).disabled
    assert any("holds 60 people" in e.value for e in app.error)


def test_valid_request_is_submitted_as_pending(app, db_path):
    fill(app, db_path, "Main Auditorium", date(2026, 8, 5), time(14), time(16), 300)
    assert not submit_button(app).disabled
    assert any("Main Auditorium is available" in s.value for s in app.success)

    submit_button(app).click().run()

    assert not app.exception
    assert any("submitted and is now PENDING" in s.value for s in app.success)
    assert app.text_input(key="req_title").value == ""
    new = [e for e in events(db_path) if e.title == "Tech Talk"]
    assert len(new) == 1
    assert new[0].status is Status.PENDING
    assert new[0].organiser == "Coding Club"


def test_slot_is_held_after_submission(app, db_path):
    fill(app, db_path, "Main Auditorium", date(2026, 8, 5), time(14), time(16), 300)
    submit_button(app).click().run()
    fill(app, db_path, "Main Auditorium", date(2026, 8, 5), time(15), time(17), 100, title="Another")
    assert submit_button(app).disabled
    assert any("(PENDING)" in e.value for e in app.error)


def test_organiser_sees_and_cancels_own_confirmed_event(app, db_path):
    app.sidebar.text_input(key="actor_REQUESTER").input("AI Club").run()
    cancel = app.button(key="cancel_1")  # seeded Seminar Hall A event
    assert any("Intro to Machine Learning Workshop" in m.value for m in app.markdown)

    cancel.click().run()

    assert not app.exception
    assert any("cancelled" in s.value for s in app.success)
    seeded = [e for e in events(db_path) if e.id == 1][0]
    assert seeded.status is Status.CANCELLED


def test_other_organisers_have_no_requests(app):
    app.sidebar.text_input(key="actor_REQUESTER").input("Nobody Club").run()
    assert any("No requests found" in i.value for i in app.info)


def test_blank_name_shows_warning(app):
    app.sidebar.text_input(key="actor_REQUESTER").input("   ").run()
    assert any("Enter your name" in w.value for w in app.warning)


@pytest.mark.parametrize("role", ["Reviewer", "Facilities Manager"])
def test_other_roles_render_without_error(app, role):
    app.sidebar.radio(key="role").set_value(role).run()
    assert not app.exception
    assert app.header[0].value == role
