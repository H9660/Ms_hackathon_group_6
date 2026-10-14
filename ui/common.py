"""Small UI helpers shared by all pages."""

from __future__ import annotations

import streamlit as st

from cems.models import Event, Status, Venue
from cems.rules import format_window

STATUS_COLOURS = {
    Status.PENDING: "orange",
    Status.CONFIRMED: "green",
    Status.REJECTED: "red",
    Status.CANCELLED: "gray",
}

_FLASH_KEY = "_flash"


def status_badge(status: Status) -> str:
    """Markdown for a coloured status label."""
    return f":{STATUS_COLOURS[status]}-badge[{status.value}]"


def venue_label(venue: Venue) -> str:
    return f"{venue.name} · {venue.type} · {venue.capacity} seats"


def set_flash(kind: str, messages: list[str] | str) -> None:
    """Queue a message to show on the next rerun (used from button callbacks)."""
    st.session_state[_FLASH_KEY] = (kind, [messages] if isinstance(messages, str) else messages)


def show_flash() -> None:
    """Show and clear the queued message, if any."""
    flash = st.session_state.pop(_FLASH_KEY, None)
    if flash:
        kind, messages = flash
        show_messages(kind, messages)


def show_messages(kind: str, messages: list[str]) -> None:
    """Render messages as one success / error / warning / info box."""
    box = {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)
    if len(messages) == 1:
        box(messages[0])
    else:
        box("\n".join(f"- {m}" for m in messages))


def event_summary(event: Event, venue: Venue | None) -> str:
    where = venue.name if venue else f"venue #{event.venue_id}"
    return f"{where} · {format_window(event.start, event.end)} · {event.attendees} attendees"
