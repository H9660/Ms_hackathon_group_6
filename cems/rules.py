"""Business validations.

Every check returns a list of human-readable reasons; an empty list means the
action is allowed. Rules only read from the database, never write, so the UI
can call them freely for a live pre-check before anything is submitted
(business condition 3) and services can re-run them inside a transaction.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from cems import repository as repo
from cems.models import EVENT_TYPES, Event, Role, Status, Venue

MAX_DURATION = timedelta(hours=12)


def format_window(start: datetime, end: datetime) -> str:
    """'04 Aug 2026 10:00–12:00', or both dates when the window spans days."""
    if start.date() == end.date():
        return f"{start:%d %b %Y %H:%M}–{end:%H:%M}"
    return f"{start:%d %b %Y %H:%M} – {end:%d %b %Y %H:%M}"


def validate_time_window(start: datetime | None, end: datetime | None) -> list[str]:
    """Condition 1: an event has a defined start and end, in the right order."""
    if start is None or end is None:
        return ["Start and end date-time are both required."]
    if end <= start:
        return ["End time must be after the start time."]
    if end - start > MAX_DURATION:
        hours = int(MAX_DURATION.total_seconds() // 3600)
        return [f"An event can last at most {hours} hours."]
    return []


def validate_capacity(venue: Venue, attendees: int) -> list[str]:
    """Condition 10: the selected venue must be able to hold the audience."""
    if attendees <= 0:
        return ["Expected attendees must be at least 1."]
    if attendees > venue.capacity:
        return [
            f"{venue.name} holds {venue.capacity} people; "
            f"{attendees} expected attendees exceed its capacity."
        ]
    return []


def check_availability(
    conn: sqlite3.Connection,
    venue: Venue,
    start: datetime,
    end: datetime,
    exclude_event_id: int | None = None,
) -> list[str]:
    """Conditions 2 and 4: no overlapping active booking and no venue block.

    ``exclude_event_id`` lets a pending request be re-checked on approval
    without conflicting with itself.
    """
    reasons = [
        f"{venue.name} is already booked {format_window(e.start, e.end)} "
        f"for '{e.title}' ({e.status.value})."
        for e in repo.find_overlapping_events(conn, venue.id, start, end, exclude_event_id)
    ]
    reasons += [
        f"{venue.name} is unavailable {format_window(b.start, b.end)} ({b.reason})."
        for b in repo.find_overlapping_blocks(conn, venue.id, start, end)
    ]
    return reasons


def validate_request(
    conn: sqlite3.Connection,
    title: str,
    organiser: str,
    event_type: str,
    venue_id: int | None,
    start: datetime | None,
    end: datetime | None,
    attendees: int,
) -> list[str]:
    """All checks a new event request must pass before it can be submitted.

    Returns every problem found (not just the first) so the requester can fix
    them in one go. Checks that depend on an earlier one (capacity needs a
    venue; availability needs a venue and a valid window) are skipped when
    that earlier check fails, to avoid misleading follow-on messages.
    """
    reasons: list[str] = []
    if not (title or "").strip():
        reasons.append("Event title is required.")
    if not (organiser or "").strip():
        reasons.append("Organiser name is required.")
    if event_type not in EVENT_TYPES:
        reasons.append(f"Event type must be one of: {', '.join(EVENT_TYPES)}.")

    window_errors = validate_time_window(start, end)
    reasons += window_errors

    venue = repo.get_venue(conn, venue_id) if venue_id is not None else None
    if venue is None:
        reasons.append("Please select an existing venue.")
        return reasons

    reasons += validate_capacity(venue, attendees)
    if not window_errors:
        reasons += check_availability(conn, venue, start, end)
    return reasons


def can_cancel(event: Event, actor_name: str, actor_role: Role | str) -> list[str]:
    """Condition 7: only a confirmed event, and only its organiser or a Reviewer."""
    if event.status is not Status.CONFIRMED:
        return [f"Only confirmed events can be cancelled (this event is {event.status.value})."]
    if Role(actor_role) is Role.REVIEWER:
        return []
    is_organiser = (actor_name or "").strip().casefold() == event.organiser.strip().casefold()
    if Role(actor_role) is Role.REQUESTER and is_organiser:
        return []
    return [f"Only the organiser ({event.organiser}) or a Reviewer can cancel this event."]
