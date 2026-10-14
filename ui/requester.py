"""Requester page: submit a venue request and track / cancel your own events.

Business condition 3 (prevent conflicts *before* submission): the form uses
plain widgets rather than ``st.form`` so every change reruns the script and
``rules.validate_request`` is evaluated live. The Submit button stays
disabled while any problem is listed.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

import streamlit as st

from cems import repository as repo
from cems import rules, services
from cems.models import ACTIVE_STATUSES, EVENT_TYPES, Role, Status
from cems.services import BookingError
from ui.common import event_summary, set_flash, show_flash, status_badge, venue_label

# Seed data is in early Aug 2026, so default the form there for demos (A4).
DEFAULT_DATE = date(2026, 8, 4)


def render(conn: sqlite3.Connection, actor: str) -> None:
    st.header("Requester")
    show_flash()
    if not actor:
        st.warning("Enter your name or club in the sidebar to make requests.")
        return
    new_tab, mine_tab = st.tabs(["New request", "My requests"])
    with new_tab:
        _new_request(conn, actor)
    with mine_tab:
        _my_requests(conn, actor)


# --------------------------------------------------------------------------
# New request
# --------------------------------------------------------------------------

def _new_request(conn: sqlite3.Connection, organiser: str) -> None:
    venues = {v.id: v for v in repo.list_venues(conn)}

    left, right = st.columns(2)
    with left:
        title = st.text_input("Event title", key="req_title")
        event_type = st.selectbox("Event type", EVENT_TYPES, key="req_type")
        venue_id = st.selectbox(
            "Venue", list(venues), format_func=lambda vid: venue_label(venues[vid]), key="req_venue"
        )
        attendees = st.number_input(
            "Expected attendees", min_value=1, value=50, step=10, key="req_attendees"
        )
    with right:
        day = st.date_input("Date", value=DEFAULT_DATE, key="req_date")
        start_t = st.time_input("Start time", value=time(10, 0), step=900, key="req_start")
        end_t = st.time_input("End time", value=time(12, 0), step=900, key="req_end")
        st.caption(f"Organiser: **{organiser}**. Change it in the sidebar.")

    start = datetime.combine(day, start_t) if day and start_t else None
    end = datetime.combine(day, end_t) if day and end_t else None

    if venue_id is not None and day:
        _venue_day_overview(conn, venues[venue_id].name, venue_id, day)

    reasons = rules.validate_request(
        conn,
        title=title,
        organiser=organiser,
        event_type=event_type,
        venue_id=venue_id,
        start=start,
        end=end,
        attendees=int(attendees),
    )
    if reasons:
        st.error("This request cannot be submitted yet:\n" + "\n".join(f"- {r}" for r in reasons))
    else:
        st.success(f"{venues[venue_id].name} is available for {rules.format_window(start, end)}.")

    st.button(
        "Submit request",
        type="primary",
        disabled=bool(reasons),
        key="req_submit",
        on_click=_submit,
        args=(conn, title, event_type, organiser, venue_id, start, end, int(attendees)),
    )


def _venue_day_overview(conn: sqlite3.Connection, venue_name: str, venue_id: int, day: date) -> None:
    """Show what already occupies the selected venue on the selected day."""
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    events = repo.find_overlapping_events(conn, venue_id, day_start, day_end)
    blocks = repo.find_overlapping_blocks(conn, venue_id, day_start, day_end)
    with st.expander(f"{venue_name} on {day:%d %b %Y}: {len(events) + len(blocks)} commitment(s)"):
        if not events and not blocks:
            st.write("Nothing booked or blocked on this day.")
        for e in events:
            st.markdown(f"{status_badge(e.status)} {rules.format_window(e.start, e.end)} · {e.title}")
        for b in blocks:
            st.markdown(f":violet-badge[BLOCKED] {rules.format_window(b.start, b.end)} · {b.reason}")


def _submit(conn, title, event_type, organiser, venue_id, start, end, attendees) -> None:
    """Button callback: runs before the rerun, so it may reset widget state."""
    try:
        event_id = services.submit_request(
            conn, title, event_type, organiser, venue_id, start, end, attendees
        )
    except BookingError as err:
        # Only reachable if the slot was taken between render and click.
        set_flash("error", err.reasons)
        return
    st.session_state["req_title"] = ""
    set_flash("success", f"Request #{event_id} submitted and is now PENDING review.")


# --------------------------------------------------------------------------
# My requests
# --------------------------------------------------------------------------

def _my_requests(conn: sqlite3.Connection, organiser: str) -> None:
    me = organiser.strip().casefold()
    mine = [e for e in repo.list_events(conn) if e.organiser.casefold() == me]
    if not mine:
        st.info(f"No requests found for **{organiser}**.")
        return

    counts = {s: sum(e.status is s for e in mine) for s in Status}
    for col, status in zip(st.columns(len(Status)), Status):
        col.metric(status.value.title(), counts[status])

    venues = {v.id: v for v in repo.list_venues(conn)}
    # Active requests first, then by start time.
    mine.sort(key=lambda e: (e.status not in ACTIVE_STATUSES, e.start))
    for event in mine:
        with st.container(border=True):
            st.markdown(f"{status_badge(event.status)} **#{event.id} {event.title}** · {event.event_type}")
            st.caption(event_summary(event, venues.get(event.venue_id)))
            if event.status is Status.REJECTED and event.reject_reason:
                st.markdown(f"Rejection reason: _{event.reject_reason}_")
            if event.status is Status.CONFIRMED:
                st.button(
                    "Cancel event",
                    key=f"cancel_{event.id}",
                    on_click=_cancel,
                    args=(conn, event.id, organiser),
                )


def _cancel(conn: sqlite3.Connection, event_id: int, organiser: str) -> None:
    try:
        services.cancel_event(conn, event_id, organiser, Role.REQUESTER)
    except BookingError as err:
        set_flash("error", err.reasons)
        return
    set_flash("success", f"Event #{event_id} cancelled. The venue is available again.")
