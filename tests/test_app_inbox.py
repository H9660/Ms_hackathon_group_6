"""UI tests for the notification inboxes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from cems import notifications as notify
from cems import repository as repo
from cems import services
from cems.db import get_conn, init_db
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


def open_as(role) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    if role != "Requester":
        at.sidebar.radio(key="role").set_value(role).run()
    assert not at.exception
    return at


def tab_labels(at):
    return [t.label for t in at.tabs]


def test_empty_inbox(db_path):
    at = open_as("Requester")
    assert "Inbox" in tab_labels(at)
    assert any("No notifications yet" in i.value for i in at.info)


def test_reviewer_inbox_shows_new_request(db_path):
    event_id = submit_pending(db_path)
    at = open_as("Reviewer")
    assert "Inbox (1 new)" in tab_labels(at)
    assert any(f"New request #{event_id}" in m.value for m in at.markdown)


def test_approval_from_reviewer_page_reaches_requester_inbox(db_path):
    event_id = submit_pending(db_path)
    at = open_as("Reviewer")
    at.button(key=f"approve_{event_id}").click().run()

    at.sidebar.radio(key="role").set_value("Requester").run()  # default name: Coding Club
    assert not at.exception
    assert "Inbox (1 new)" in tab_labels(at)
    assert any("was approved by Events Office" in m.value for m in at.markdown)


def test_mark_all_as_read(db_path):
    submit_pending(db_path)
    at = open_as("Reviewer")
    at.button(key="rev_inbox_mark_all").click().run()

    assert not at.exception
    assert "Inbox" in tab_labels(at)
    assert at.button(key="rev_inbox_mark_all").disabled
    assert with_db(db_path, lambda c: notify.unread_count(c, notify.REVIEWER_INBOX)) == 0
