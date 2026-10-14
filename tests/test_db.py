import sqlite3

import pytest

from cems.db import TABLES_CHILD_FIRST, clear_all, init_db, transaction


def _tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r["name"] for r in rows}


def test_schema_creates_all_tables(empty_conn):
    assert set(TABLES_CHILD_FIRST) <= _tables(empty_conn)


def test_init_db_is_idempotent(empty_conn):
    init_db(empty_conn)
    init_db(empty_conn)
    assert set(TABLES_CHILD_FIRST) <= _tables(empty_conn)


def test_foreign_keys_are_enforced(empty_conn):
    with pytest.raises(sqlite3.IntegrityError):
        empty_conn.execute(
            "INSERT INTO venue_blocks (venue_id, start_at, end_at, reason) "
            "VALUES (999, '2026-08-04T09:00', '2026-08-04T10:00', 'x')"
        )


def test_event_end_must_be_after_start(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO events (title, event_type, organiser, venue_id, start_at, end_at, attendees, status) "
            "VALUES ('t', 'Workshop', 'o', 1, '2026-08-04T12:00', '2026-08-04T10:00', 10, 'PENDING')"
        )


def test_unknown_status_is_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO events (title, event_type, organiser, venue_id, start_at, end_at, attendees, status) "
            "VALUES ('t', 'Workshop', 'o', 1, '2026-08-04T10:00', '2026-08-04T12:00', 10, 'APPROVED')"
        )


def test_venue_capacity_must_be_positive(empty_conn):
    with pytest.raises(sqlite3.IntegrityError):
        empty_conn.execute("INSERT INTO venues (name, type, capacity) VALUES ('X', 'Hall', 0)")


def test_transaction_commits_on_success(empty_conn):
    with transaction(empty_conn):
        empty_conn.execute("INSERT INTO venues (name, type, capacity) VALUES ('X', 'Hall', 10)")
    assert empty_conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 1


def test_transaction_rolls_back_on_error(empty_conn):
    with pytest.raises(RuntimeError):
        with transaction(empty_conn, immediate=True):
            empty_conn.execute("INSERT INTO venues (name, type, capacity) VALUES ('X', 'Hall', 10)")
            raise RuntimeError("boom")
    assert empty_conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 0
    assert not empty_conn.in_transaction


def test_nested_transaction_joins_outer_and_rolls_back_together(empty_conn):
    with pytest.raises(RuntimeError):
        with transaction(empty_conn):
            with transaction(empty_conn):
                empty_conn.execute("INSERT INTO venues (name, type, capacity) VALUES ('X', 'Hall', 10)")
            raise RuntimeError("outer fails")
    assert empty_conn.execute("SELECT COUNT(*) FROM venues").fetchone()[0] == 0


def test_clear_all_empties_every_table(conn):
    clear_all(conn)
    for table in TABLES_CHILD_FIRST:
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
