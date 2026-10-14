"""Streamlit entry point: ``streamlit run app.py``.

There is no authentication (assumption A6): the sidebar selects the acting
role and name. Set ``CEMS_DB_PATH`` to use a database file other than the
default ``cems.db``.
"""

from __future__ import annotations

import os
import sqlite3

import streamlit as st

from cems.db import DEFAULT_DB_PATH, get_conn, init_db
from cems.models import Role
from cems.seed import reset_db, seed
from ui import facilities, requester, reviewer, schedule
from ui.common import set_flash

DEFAULT_ACTORS = {
    Role.REQUESTER: "Coding Club",
    Role.REVIEWER: "Events Office",
    Role.FACILITIES: "Facilities Office",
}


@st.cache_resource
def connection(path: str) -> sqlite3.Connection:
    """One shared connection per database file, created and seeded on first use."""
    conn = get_conn(path)
    init_db(conn)
    seed(conn)
    return conn


SCHEDULE = "Campus schedule"  # read-only view for everyone; needs no name

PAGES = {
    Role.REQUESTER: requester.render,
    Role.REVIEWER: reviewer.render,
    Role.FACILITIES: facilities.render,
}


def _reset(conn: sqlite3.Connection) -> None:
    reset_db(conn)
    set_flash("success", "Demo data reset to the initial campus data.")


def main() -> None:
    st.set_page_config(page_title="Campus Event Management", page_icon="📅", layout="wide")
    conn = connection(os.environ.get("CEMS_DB_PATH", str(DEFAULT_DB_PATH)))

    with st.sidebar:
        st.title("📅 Campus Events")
        choice = st.radio("Acting as", [r.value for r in Role] + [SCHEDULE], key="role")
        role = None if choice == SCHEDULE else Role(choice)
        actor = ""
        if role is not None:
            actor = st.text_input(
                "Your name / club", value=DEFAULT_ACTORS[role], key=f"actor_{role.name}"
            ).strip()
        st.caption("Prototype: no login. Choose a role and name to act as.")
        st.divider()
        st.button(
            "Reset demo data",
            key="reset_demo",
            help="Delete all requests and blocks and reload the initial campus data.",
            on_click=_reset,
            args=(conn,),
        )

    if role is None:
        schedule.render(conn)
    else:
        PAGES[role](conn, actor)


main()
