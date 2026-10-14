"""Facilities Manager page: venue overview and maintenance / renovation blocks
(business condition 4)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time

import streamlit as st

from cems import repository as repo
from cems import venue_service
from cems.rules import format_window
from cems.services import BookingError
from ui.common import set_flash, show_flash, venue_label

DEFAULT_DATE = date(2026, 8, 4)


def render(conn: sqlite3.Connection, actor: str) -> None:
    st.header("Facilities Manager")
    show_flash()
    venues = {v.id: v for v in repo.list_venues(conn)}

    venues_tab, block_tab = st.tabs(["Venues & blocks", "Block a venue"])
    with venues_tab:
        _venues_and_blocks(conn, venues)
    with block_tab:
        _block_form(conn, venues)


def _venues_and_blocks(conn, venues) -> None:
    st.dataframe(
        [{"Venue": v.name, "Type": v.type, "Capacity": v.capacity} for v in venues.values()],
        hide_index=True,
    )
    st.subheader("Current blocks")
    blocks = repo.list_blocks(conn)
    if not blocks:
        st.info("No venues are blocked.")
    for block in blocks:
        with st.container(border=True):
            info_col, action_col = st.columns([4, 1], vertical_alignment="center")
            info_col.markdown(
                f":violet-badge[BLOCKED] **{venues[block.venue_id].name}** · "
                f"{format_window(block.start, block.end)} · {block.reason}"
            )
            action_col.button(
                "Remove block",
                key=f"unblock_{block.id}",
                on_click=_remove,
                args=(conn, block.id),
            )


def _block_form(conn, venues) -> None:
    venue_id = st.selectbox(
        "Venue", list(venues), format_func=lambda vid: venue_label(venues[vid]), key="blk_venue"
    )
    left, right = st.columns(2)
    with left:
        start_day = st.date_input("From date", value=DEFAULT_DATE, key="blk_start_date")
        start_t = st.time_input("From time", value=time(9, 0), step=900, key="blk_start_time")
    with right:
        end_day = st.date_input("To date", value=DEFAULT_DATE, key="blk_end_date")
        end_t = st.time_input("To time", value=time(18, 0), step=900, key="blk_end_time")
    kind = st.selectbox("Reason", venue_service.BLOCK_REASONS, key="blk_reason")
    notes = st.text_input("Details (optional)", key="blk_notes", placeholder="e.g. projector replacement")

    start = datetime.combine(start_day, start_t) if start_day and start_t else None
    end = datetime.combine(end_day, end_t) if end_day and end_t else None
    reason = f"{kind}: {notes.strip()}" if notes.strip() else kind

    # Preview the bookings that would prevent this block.
    if venue_id is not None and start and end and end > start:
        clashes = repo.find_overlapping_events(conn, venue_id, start, end)
        if clashes:
            st.warning(
                f"{len(clashes)} active booking(s) in this period. Cancel or reject them first:\n"
                + "\n".join(f"- #{e.id} {e.title}, {format_window(e.start, e.end)} ({e.status.value})"
                            for e in clashes)
            )

    st.button(
        "Block venue",
        type="primary",
        key="blk_submit",
        on_click=_add,
        args=(conn, venue_id, start, end, reason),
    )


def _add(conn, venue_id, start, end, reason) -> None:
    try:
        block_id = venue_service.add_block(conn, venue_id, start, end, reason)
    except BookingError as err:
        set_flash("error", err.reasons)
        return
    st.session_state["blk_notes"] = ""
    set_flash("success", f"Block #{block_id} added. The venue cannot be booked in that period.")


def _remove(conn, block_id: int) -> None:
    try:
        venue_service.remove_block(conn, block_id)
    except BookingError as err:
        set_flash("error", err.reasons)
        return
    set_flash("success", f"Block #{block_id} removed. The venue can be booked again.")
