# CLAUDE.md

Guidance for AI assistants (Claude, Copilot) working in this repository.

## Project

Campus Event Management System: a hackathon prototype in Python 3.10+, Streamlit and SQLite (stdlib `sqlite3`).
The team works in **7 sequential steps, one member per step and one commit per step**. See [PLAN.md](PLAN.md) for:
- §2: business rules and assumptions
- §3: the interface contract (agreed function signatures)
- §5: the scope of each step

Do not implement a later step's work early, and do not change the signatures in the contract without the team agreeing.

## Commands

```bash
pip install -r requirements.txt
pytest -q                     # must pass before every commit
python -m cems.seed [--reset] # create / reset the local cems.db
streamlit run app.py          # UI (from Step 4)
```

## Architecture: strict layering

Each layer imports only from the layers below it:

```
ui/*  ->  services.py  ->  rules.py  ->  repository.py  ->  db.py  ->  models.py
```

- `models.py`: dataclasses and enums only. No I/O.
- `db.py`: connection, schema, `transaction()`, `clear_all()`. If you add a table, also add it to `TABLES_CHILD_FIRST`.
- `repository.py`: SQL ↔ dataclass mapping. **No business rules, and it never commits.**
- `rules.py`: validations that return a `list[str]` of human-readable reasons (an empty list means valid). Rules never write.
- `services.py`: state transitions. Owns transactions (`with transaction(conn, immediate=True):`) and writes to the audit log.
- `ui/*`: Streamlit only. Writes go through `services` (catch `BookingError` and show `.reasons`); reads may use `repository`; never runs SQL directly.

## Conventions

- Datetimes: Python `datetime` in code; `models.to_db` / `from_db` (`YYYY-MM-DDTHH:MM`) at the DB boundary. DB columns are `start_at` / `end_at` (`end` is an SQL keyword).
- Overlap test (half-open intervals): `a.start < b.end AND b.start < a.end`. Back-to-back bookings are allowed. Never use `<=`.
- Only `ACTIVE_STATUSES` (PENDING, CONFIRMED) hold a venue. Rejecting or cancelling releases it automatically.
- When re-checking an existing request (e.g. on approval), call `rules.check_availability(..., exclude_event_id=event.id)` so it does not conflict with itself.
- Roles are `models.Role`. The assumptions are listed in `docs/ASSUMPTIONS.md`; update that file when you add a new one.
- Always use parameterised SQL (`?` placeholders). Never build SQL from user input with f-strings.
- Tests use the `conn` fixture (in-memory DB plus seed data) or `empty_conn` (schema only) from `tests/conftest.py`.
- Type hints on all public functions; `from __future__ import annotations` at the top of each module.
- Commit messages: `<type>(<area>): <message>`. Types: feat, fix, test, docs, chore, refactor.
- Each step adds `docs/contributions/mN.md`.
