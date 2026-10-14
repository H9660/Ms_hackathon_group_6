"""Shared fixtures: every test gets its own fresh in-memory database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from cems.db import get_conn, init_db
from cems.seed import seed


@pytest.fixture
def empty_conn() -> Iterator[sqlite3.Connection]:
    """Schema only, no data."""
    conn = get_conn(":memory:")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def conn(empty_conn: sqlite3.Connection) -> sqlite3.Connection:
    """Schema plus the initial campus data from the problem statement."""
    seed(empty_conn)
    return empty_conn
