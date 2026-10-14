"""Domain model: statuses, event types and the core dataclasses.

This module has no dependencies on the database or UI so that every other
layer (and every test) can import it freely.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# All date-times are stored with minute precision in this ISO-like format.
# Strings in this format sort chronologically, so SQL range comparisons work
# directly on the stored text.
DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class Status(str, Enum):
    """Lifecycle status of an event request.

    PENDING --approve--> CONFIRMED --cancel--> CANCELLED
    PENDING --reject---> REJECTED (closed; revisions need a new request)
    """

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# Statuses that hold a venue. REJECTED / CANCELLED release it automatically
# because conflict checks only consider these.
ACTIVE_STATUSES: tuple[Status, ...] = (Status.PENDING, Status.CONFIRMED)

class Role(str, Enum):
    """Who is acting. There is no authentication; the UI selects a role."""

    REQUESTER = "Requester"
    REVIEWER = "Reviewer"
    FACILITIES = "Facilities Manager"


EVENT_TYPES: list[str] = [
    "Workshop",
    "Hackathon",
    "Placement",
    "Club",
    "Cultural",
    "Competition",
]


def to_db(value: datetime) -> str:
    """Serialise a datetime for storage (minute precision)."""
    return value.strftime(DATETIME_FORMAT)


def from_db(value: str) -> datetime:
    """Parse a stored datetime string."""
    return datetime.strptime(value, DATETIME_FORMAT)


@dataclass
class Venue:
    id: int | None
    name: str
    type: str
    capacity: int


@dataclass
class Event:
    id: int | None
    title: str
    event_type: str
    organiser: str
    venue_id: int
    start: datetime
    end: datetime
    attendees: int
    status: Status
    reject_reason: str | None = None


@dataclass
class VenueBlock:
    """A period during which a venue is unavailable (maintenance, renovation...)."""

    id: int | None
    venue_id: int
    start: datetime
    end: datetime
    reason: str


@dataclass
class AuditEntry:
    """One recorded action on an event (submitted, approved, rejected...)."""

    id: int
    event_id: int
    action: str
    actor: str
    detail: str
    created_at: str
