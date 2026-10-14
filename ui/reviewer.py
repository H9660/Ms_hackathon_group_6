"""Reviewer page (Events Office): approve / reject pending requests and cancel
confirmed events (business conditions 5-8)."""

from __future__ import annotations

import sqlite3

import streamlit as st

from cems import repository as repo
from cems import notifications, rules, services
from cems.models import Event, Role, Status, Venue
from cems.services import BookingError
from ui import inbox
from ui.common import event_summary, set_flash, show_flash, status_badge


def render(conn: sqlite3.Connection, actor: str) -> None:
    st.header("Reviewer")
    show_flash()
    if not actor:
        st.warning("Enter your name in the sidebar to review requests.")
        return

    venues = {v.id: v for v in repo.list_venues(conn)}
    pending = repo.list_events(conn, status=Status.PENDING)
    confirmed = repo.list_events(conn, status=Status.CONFIRMED)

    pending_tab, confirmed_tab, all_tab, inbox_tab = st.tabs(
        [
            f"Pending review ({len(pending)})",
            f"Confirmed ({len(confirmed)})",
            "All requests",
            inbox.tab_label(conn, notifications.REVIEWER_INBOX),
        ]
    )
    with pending_tab:
        _pending(conn, actor, pending, venues)
    with confirmed_tab:
        _confirmed(conn, actor, confirmed, venues)
    with all_tab:
        _all_requests(conn, venues)
    with inbox_tab:
        st.caption("Shared inbox for all reviewers.")
        inbox.render(conn, notifications.REVIEWER_INBOX, key="rev_inbox")


def _history(conn: sqlite3.Connection, event: Event) -> None:
    with st.expander("History"):
        for h in repo.get_history(conn, event.id):
            detail = f" · {h.detail}" if h.detail else ""
            st.markdown(f"`{h.created_at}` **{h.action}** by {h.actor}{detail}")


def _pending(conn, actor: str, pending: list[Event], venues: dict[int, Venue]) -> None:
    if not pending:
        st.info("No requests are waiting for review.")
        return
    for event in pending:
        venue = venues[event.venue_id]
        with st.container(border=True):
            st.markdown(
                f"{status_badge(event.status)} **#{event.id} {event.title}** · "
                f"{event.event_type} · by **{event.organiser}**"
            )
            st.caption(f"{event_summary(event, venue)} (capacity {venue.capacity})")

            # Same re-check the service runs on approval, shown up front.
            conflicts = rules.check_availability(
                conn, venue, event.start, event.end, exclude_event_id=event.id
            )
            if conflicts:
                st.warning("Cannot be approved:\n" + "\n".join(f"- {c}" for c in conflicts))

            approve_col, reason_col, reject_col = st.columns([1, 3, 1], vertical_alignment="bottom")
            approve_col.button(
                "Approve",
                type="primary",
                key=f"approve_{event.id}",
                disabled=bool(conflicts),
                on_click=_approve,
                args=(conn, event.id, actor),
            )
            reason = reason_col.text_input(
                "Rejection reason", key=f"reason_{event.id}", placeholder="Required to reject"
            )
            reject_col.button(
                "Reject",
                key=f"reject_{event.id}",
                disabled=not reason.strip(),
                on_click=_reject,
                args=(conn, event.id, actor, reason),
            )
            _history(conn, event)


def _confirmed(conn, actor: str, confirmed: list[Event], venues: dict[int, Venue]) -> None:
    if not confirmed:
        st.info("No confirmed events.")
        return
    for event in confirmed:
        with st.container(border=True):
            st.markdown(
                f"{status_badge(event.status)} **#{event.id} {event.title}** · by **{event.organiser}**"
            )
            st.caption(event_summary(event, venues.get(event.venue_id)))
            st.button(
                "Cancel event",
                key=f"rev_cancel_{event.id}",
                on_click=_cancel,
                args=(conn, event.id, actor),
            )
            _history(conn, event)


def _all_requests(conn, venues: dict[int, Venue]) -> None:
    rows = [
        {
            "ID": e.id,
            "Title": e.title,
            "Organiser": e.organiser,
            "Venue": venues[e.venue_id].name,
            "When": rules.format_window(e.start, e.end),
            "Attendees": e.attendees,
            "Status": e.status.value,
            "Rejection reason": e.reject_reason or "",
        }
        for e in repo.list_events(conn)
    ]
    st.dataframe(rows, hide_index=True)


# --------------------------------------------------------------- callbacks

def _run(action, success: str) -> None:
    try:
        action()
    except BookingError as err:
        set_flash("error", err.reasons)
        return
    set_flash("success", success)


def _approve(conn, event_id: int, actor: str) -> None:
    _run(lambda: services.approve_request(conn, event_id, actor),
         f"Request #{event_id} approved and is now CONFIRMED.")


def _reject(conn, event_id: int, actor: str, reason: str) -> None:
    _run(lambda: services.reject_request(conn, event_id, actor, reason),
         f"Request #{event_id} rejected. The venue slot has been released.")


def _cancel(conn, event_id: int, actor: str) -> None:
    _run(lambda: services.cancel_event(conn, event_id, actor, Role.REVIEWER),
         f"Event #{event_id} cancelled. The venue slot has been released.")
