"""Campus schedule: who is using which venue, and when (visible to everyone).

Addresses the brief's "limited visibility" pain point for the whole campus
community, not only requesters and reviewers.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from cems import repository as repo
from cems.models import ACTIVE_STATUSES, Status
from cems.rules import format_window

DEFAULT_DATE = date(2026, 8, 4)

# Reserved status colours: state is encoded by colour *and* by the legend,
# tooltip and table, never by colour alone.
STATE_COLOURS = {
    "CONFIRMED": "#0ca30c",  # good
    "PENDING": "#fab219",    # warning
    "BLOCKED": "#d03b3b",    # critical: venue unavailable
    "REJECTED": "#9e9e9e",   # released, shown only on request
    "CANCELLED": "#bdbdbd",
}


def render(conn: sqlite3.Connection, actor: str = "") -> None:
    st.header("Campus schedule")
    venues = repo.list_venues(conn)

    left, right = st.columns([1, 2], vertical_alignment="bottom")
    day = left.date_input("Date", value=DEFAULT_DATE, key="sched_date")
    show_released = right.checkbox(
        "Show rejected and cancelled requests", key="sched_released"
    )
    if not day:
        return

    rows = _day_rows(conn, venues, day, show_released)
    _day_chart(rows, [v.name for v in venues], day)

    busy = {r["Venue"] for r in rows if r["State"] in ("CONFIRMED", "PENDING", "BLOCKED")}
    free = [v.name for v in venues if v.name not in busy]
    if free:
        st.success("Free all day: " + ", ".join(free))

    st.subheader(f"Commitments on {day:%d %b %Y}")
    if rows:
        st.dataframe(
            pd.DataFrame(rows)[["Venue", "When", "State", "What", "Capacity"]],
            hide_index=True,
        )
    else:
        st.info("No bookings or blocks on this day.")

    st.subheader("All confirmed events")
    _confirmed_table(conn, {v.id: v for v in venues})


def _day_rows(conn, venues, day: date, show_released: bool) -> list[dict]:
    day_start = datetime.combine(day, time.min)
    day_end = day_start + timedelta(days=1)
    statuses = list(Status) if show_released else list(ACTIVE_STATUSES)
    rows: list[dict] = []
    for venue in venues:
        for e in repo.list_events(conn, venue_id=venue.id):
            if e.status in statuses and e.start < day_end and day_start < e.end:
                rows.append(_row(venue, e.start, e.end, e.status.value,
                                 f"{e.title} ({e.organiser}, {e.attendees} attendees)"))
        for b in repo.find_overlapping_blocks(conn, venue.id, day_start, day_end):
            rows.append(_row(venue, b.start, b.end, "BLOCKED", b.reason))
    rows.sort(key=lambda r: (r["Venue"], r["start"]))
    return rows


def _row(venue, start: datetime, end: datetime, state: str, what: str) -> dict:
    return {
        "Venue": venue.name,
        "Capacity": venue.capacity,
        "start": start,
        "end": end,
        "When": format_window(start, end),
        "State": state,
        "What": what,
    }


def _day_chart(rows: list[dict], venue_names: list[str], day: date) -> None:
    """Timeline: one row per venue (all venues, so free ones are visible)."""
    day_start = datetime.combine(day, time.min)
    lo = min([day_start + timedelta(hours=7)] + [max(r["start"], day_start) for r in rows])
    hi = max([day_start + timedelta(hours=22)] +
             [min(r["end"], day_start + timedelta(days=1)) for r in rows])

    data = pd.DataFrame(
        [{**r, "start": max(r["start"], lo), "end": min(r["end"], hi)} for r in rows]
        or [{"Venue": venue_names[0], "start": lo, "end": lo, "State": "CONFIRMED",
             "When": "", "What": ""}]
    )
    states = [s for s in STATE_COLOURS if s in set(data["State"])] if rows else ["CONFIRMED"]

    chart = (
        alt.Chart(data)
        .mark_bar(cornerRadius=4, height=18)
        .encode(
            x=alt.X("start:T", title=None, scale=alt.Scale(domain=[lo, hi]),
                    axis=alt.Axis(format="%H:%M", grid=True, gridOpacity=0.3)),
            x2="end:T",
            y=alt.Y("Venue:N", title=None, sort=venue_names,
                    scale=alt.Scale(domain=venue_names)),
            color=alt.Color(
                "State:N",
                scale=alt.Scale(domain=states, range=[STATE_COLOURS[s] for s in states]),
                legend=alt.Legend(orient="top", title=None) if rows else None,
            ),
            tooltip=["Venue:N", "When:N", "State:N", "What:N"],
        )
        .properties(height=48 * len(venue_names))
    )
    st.altair_chart(chart)


def _confirmed_table(conn, venues) -> None:
    confirmed = repo.list_events(conn, status=Status.CONFIRMED)
    if not confirmed:
        st.info("No confirmed events.")
        return
    st.dataframe(
        [
            {
                "When": format_window(e.start, e.end),
                "Event": e.title,
                "Type": e.event_type,
                "Organiser": e.organiser,
                "Venue": venues[e.venue_id].name,
                "Attendees": e.attendees,
            }
            for e in confirmed
        ],
        hide_index=True,
    )
