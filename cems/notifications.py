"""In-app notifications (bonus feature, Step 6).

Addresses two pain points from the brief: "limited visibility into request
status" (organisers are told the outcome of their requests) and "delays in
reviewing" (reviewers are told when a new request is waiting).

Recipients are organiser names (matched case-insensitively, as in A9) or the
shared ``REVIEWER_INBOX``. Like the repository, these functions never commit:
services call ``notify`` inside their transaction, so a notification exists
if and only if the transition it describes happened.
"""

from __future__ import annotations

import sqlite3

from cems.models import Notification, Role

# All reviewers share one inbox, addressed by role rather than by person.
REVIEWER_INBOX = Role.REVIEWER.value


def _to_notification(row: sqlite3.Row) -> Notification:
    return Notification(
        id=row["id"],
        recipient=row["recipient"],
        message=row["message"],
        event_id=row["event_id"],
        is_read=bool(row["is_read"]),
        created_at=row["created_at"],
    )


def notify(
    conn: sqlite3.Connection,
    recipient: str,
    message: str,
    event_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO notifications (recipient, message, event_id) VALUES (?, ?, ?)",
        (recipient.strip(), message, event_id),
    )
    return cur.lastrowid


def list_for(
    conn: sqlite3.Connection,
    recipient: str,
    unread_only: bool = False,
) -> list[Notification]:
    """Newest first."""
    sql = "SELECT * FROM notifications WHERE recipient = ?"
    if unread_only:
        sql += " AND is_read = 0"
    rows = conn.execute(sql + " ORDER BY id DESC", ((recipient or "").strip(),)).fetchall()
    return [_to_notification(r) for r in rows]


def unread_count(conn: sqlite3.Connection, recipient: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE recipient = ? AND is_read = 0",
        ((recipient or "").strip(),),
    ).fetchone()[0]


def mark_read(conn: sqlite3.Connection, notification_id: int) -> None:
    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))


def mark_all_read(conn: sqlite3.Connection, recipient: str) -> int:
    """Returns how many notifications were marked."""
    cur = conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE recipient = ? AND is_read = 0",
        ((recipient or "").strip(),),
    )
    return cur.rowcount
