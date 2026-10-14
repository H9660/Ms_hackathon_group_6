"""Request lifecycle: the only place where event status changes.

    submit ──▶ PENDING ──approve──▶ CONFIRMED ──cancel──▶ CANCELLED
                  └──────reject(reason)──▶ REJECTED

Every operation runs in one ``BEGIN IMMEDIATE`` transaction: the write lock is
taken before the checks, so no other writer can slip a conflicting booking in
between "check" and "write", and a failure part-way leaves nothing behind.
Every successful transition is recorded in the audit log.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from cems import repository as repo
from cems import rules
from cems.db import transaction
from cems.models import Event, Role, Status


class BookingError(Exception):
    """A request or transition was refused. ``reasons`` are user-facing."""

    def __init__(self, reasons: list[str] | str):
        self.reasons = [reasons] if isinstance(reasons, str) else list(reasons)
        super().__init__("; ".join(self.reasons))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _require_actor(actor: str) -> str:
    name = (actor or "").strip()
    if not name:
        raise BookingError("Your name is required so the action can be recorded.")
    return name


def _load_event(conn: sqlite3.Connection, event_id: int) -> Event:
    event = repo.get_event(conn, event_id)
    if event is None:
        raise BookingError(f"Event request #{event_id} does not exist.")
    return event


def _require_pending(event: Event, action: str) -> None:
    if event.status is not Status.PENDING:
        raise BookingError(
            f"Only PENDING requests can be {action} (request #{event.id} is {event.status.value})."
        )


# --------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------

def submit_request(
    conn: sqlite3.Connection,
    title: str,
    event_type: str,
    organiser: str,
    venue_id: int,
    start: datetime,
    end: datetime,
    attendees: int,
) -> int:
    """Validate and store a new request as PENDING. Returns its id.

    Raises BookingError with every reason if the request cannot proceed
    (business condition 10).
    """
    with transaction(conn, immediate=True):
        reasons = rules.validate_request(
            conn,
            title=title,
            organiser=organiser,
            event_type=event_type,
            venue_id=venue_id,
            start=start,
            end=end,
            attendees=attendees,
        )
        if reasons:
            raise BookingError(reasons)

        organiser = organiser.strip()
        event_id = repo.insert_event(
            conn,
            Event(None, title.strip(), event_type, organiser, venue_id,
                  start, end, attendees, Status.PENDING),
        )
        venue = repo.get_venue(conn, venue_id)
        repo.log_action(
            conn, event_id, "SUBMITTED", organiser,
            f"{venue.name}, {rules.format_window(start, end)}, {attendees} attendees",
        )
    return event_id


def approve_request(conn: sqlite3.Connection, event_id: int, actor: str) -> None:
    """PENDING -> CONFIRMED (business condition 5).

    Availability is re-checked defensively, excluding the request itself, in
    case the venue was booked or blocked by a path that bypassed submission.
    """
    actor = _require_actor(actor)
    with transaction(conn, immediate=True):
        event = _load_event(conn, event_id)
        _require_pending(event, "approved")
        venue = repo.get_venue(conn, event.venue_id)
        conflicts = rules.check_availability(
            conn, venue, event.start, event.end, exclude_event_id=event.id
        )
        if conflicts:
            raise BookingError([f"Cannot approve request #{event.id}:", *conflicts])
        repo.update_status(conn, event.id, Status.CONFIRMED)
        repo.log_action(conn, event.id, "APPROVED", actor)


def reject_request(conn: sqlite3.Connection, event_id: int, actor: str, reason: str) -> None:
    """PENDING -> REJECTED (business condition 6).

    The request is closed and its venue slot is released (REJECTED is not an
    active status). Revisions must be submitted as a new request.
    """
    actor = _require_actor(actor)
    reason = (reason or "").strip()
    if not reason:
        raise BookingError("A reason is required to reject a request.")
    with transaction(conn, immediate=True):
        event = _load_event(conn, event_id)
        _require_pending(event, "rejected")
        repo.update_status(conn, event.id, Status.REJECTED, reason=reason)
        repo.log_action(conn, event.id, "REJECTED", actor, reason)


def cancel_event(
    conn: sqlite3.Connection,
    event_id: int,
    actor: str,
    actor_role: Role | str,
) -> None:
    """CONFIRMED -> CANCELLED (business conditions 7 and 8).

    Allowed for the event's organiser or a Reviewer; releases the venue.
    """
    actor = _require_actor(actor)
    with transaction(conn, immediate=True):
        event = _load_event(conn, event_id)
        reasons = rules.can_cancel(event, actor, actor_role)
        if reasons:
            raise BookingError(reasons)
        repo.update_status(conn, event.id, Status.CANCELLED)
        repo.log_action(conn, event.id, "CANCELLED", actor, f"by {Role(actor_role).value}")
