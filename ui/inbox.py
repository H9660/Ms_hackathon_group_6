"""Notification inbox component, shared by the Requester and Reviewer pages."""

from __future__ import annotations

import sqlite3

import streamlit as st

from cems import notifications
from ui.common import set_flash


def tab_label(conn: sqlite3.Connection, recipient: str) -> str:
    unread = notifications.unread_count(conn, recipient)
    return f"Inbox ({unread} new)" if unread else "Inbox"


def render(conn: sqlite3.Connection, recipient: str, key: str) -> None:
    """List ``recipient``'s notifications, newest first, unread highlighted."""
    items = notifications.list_for(conn, recipient)
    if not items:
        st.info("No notifications yet.")
        return

    unread = sum(not n.is_read for n in items)
    st.button(
        f"Mark all as read ({unread})",
        key=f"{key}_mark_all",
        disabled=unread == 0,
        on_click=_mark_all,
        args=(conn, recipient),
    )
    for n in items:
        with st.container(border=True):
            marker = ":blue-badge[NEW] " if not n.is_read else ""
            st.markdown(f"{marker}{n.message}")
            st.caption(n.created_at.replace("T", " "))


def _mark_all(conn: sqlite3.Connection, recipient: str) -> None:
    count = notifications.mark_all_read(conn, recipient)
    set_flash("success", f"Marked {count} notification(s) as read.")
