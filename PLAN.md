# Campus Event Management System — Team Plan (7 members, 90 min)

**Stack:** Python 3.10+, Streamlit (UI), SQLite (persistence, stdlib `sqlite3`), pytest (tests).
**Shape:** 42 small commits = **6 rounds × 7 members**, strict round-robin (M1 → M2 → … → M7 → M1 …).
So no member ever makes two commits in a row, and everyone ends with exactly 6 commits.

---

## 1. Team roles (each person owns files so parallel work rarely conflicts)

| Member | Role | Owns (primary files) | Demo talking point |
|---|---|---|---|
| **M1** | Data & persistence lead | `cems/db.py`, `cems/repository.py`, `cems/venue_service.py`, `cems/notifications.py` | Schema, overlap SQL, venue blocks |
| **M2** | Business rules owner | `cems/models.py`, `cems/rules.py` | Every validation and its message (conditions 1–4, 10) |
| **M3** | Workflow / state machine | `cems/services.py` | Submit → review → confirm/reject → cancel (conditions 5–8) |
| **M4** | Requester UI | `ui/requester.py` | Request form, live conflict pre-check, My Requests, inbox |
| **M5** | Reviewer & Facilities UI | `app.py`, `ui/reviewer.py`, `ui/facilities.py` | Review queue, approve/reject, maintenance blocks |
| **M6** | QA / testing | `tests/*` | Test strategy, edge cases, E2E scenario |
| **M7** | Docs, pitch & schedule view | `README.md`, `docs/*`, `ui/schedule.py` | Problem framing, assumptions, trade-offs, 2-slide pitch |

---

## 2. Problem understanding (agree on this in the first 5 minutes)

**Stakeholders / personas**
- **Requester:** a student club, faculty member or placement cell organiser who requests venues.
- **Event Reviewer:** the Student Affairs / Events Office. Approves or rejects pending requests.
- **Facilities Manager:** blocks venues for maintenance or renovation.
- **Campus community (viewer):** sees the venue schedule and availability.

**Event lifecycle (state machine)**
```
            submit (all validations pass)
  [new] ───────────────────────────────▶ PENDING ──approve──▶ CONFIRMED ──cancel──▶ CANCELLED
                                            │
                                            └──reject(reason)──▶ REJECTED (closed)
```
- **Active statuses** (these hold the venue): `PENDING`, `CONFIRMED`.
- **Released statuses** (these free the venue): `REJECTED`, `CANCELLED`. Releasing needs no extra code: the overlap query only looks at active statuses.

**How the brief's conditions map to code**

| # | Condition | Where it lives |
|---|---|---|
| 1 | Event has start, end and venue | `models.Event`, `rules.validate_time_window` |
| 2 | No overlapping active or confirmed bookings | `repository.find_overlapping_events` + `rules` |
| 3 | Conflicts prevented **before** submit | live pre-check in `ui/requester.py`; `services.submit_request` re-validates |
| 4 | Maintenance or renovation blocks | `venue_blocks` table, `rules` block check, `ui/facilities.py` |
| 5 | Review before confirmation | `PENDING` → `approve_request` → `CONFIRMED` |
| 6 | Reject closes the request and releases the venue; revisions need a new request | `reject_request`; there is no edit path for requests |
| 7 | Appropriate user can cancel | `rules.can_cancel` (the organiser of the event, or the Reviewer) |
| 8 | Cancel releases the venue | status becomes `CANCELLED`, which is not active |
| 9 | No partial or split bookings, no suggestions | out of scope (documented) |
| 10 | Unsatisfiable request is stopped with a clear reason | `validate_request` returns human-readable reasons |

**Assumptions** (M7 documents these, and everyone applies them the same way)
1. Overlap means `new.start < existing.end AND existing.start < new.end`. Back-to-back bookings (one ends at 12:00, the next starts at 12:00) are **allowed**.
2. Expected attendees must be no more than the venue capacity.
3. `end > start`, and the maximum duration is 12 hours.
4. **Past dates are not rejected against the real clock.** The seed data is in Aug 2026, so this rule would break the demo. State this assumption openly.
5. A maintenance block **cannot** be added over an active booking. The Facilities Manager must get the event cancelled first. This keeps condition 2 consistent.
6. No authentication. A role selector in the sidebar stands in for login, and this trade-off is documented.
7. Only `PENDING` requests can be approved or rejected. Only `CONFIRMED` events can be cancelled. Every other transition is an error.
8. Times are stored as ISO strings `YYYY-MM-DDTHH:MM`. String comparison of these strings matches chronological order.

---

## 3. Interface contract (agreed before coding, so people can build in parallel)

```python
# cems/models.py  (M2)
class Status(str, Enum): PENDING="PENDING"; CONFIRMED="CONFIRMED"; REJECTED="REJECTED"; CANCELLED="CANCELLED"
ACTIVE_STATUSES = (Status.PENDING, Status.CONFIRMED)
@dataclass class Venue: id:int; name:str; type:str; capacity:int
@dataclass class Event: id:int|None; title:str; event_type:str; organiser:str; venue_id:int
                        start:datetime; end:datetime; attendees:int; status:Status
                        reject_reason:str|None=None
@dataclass class VenueBlock: id:int|None; venue_id:int; start:datetime; end:datetime; reason:str

# cems/db.py  (M1)
get_conn(path="cems.db") -> sqlite3.Connection        # row_factory = sqlite3.Row
init_db(conn) -> None                                  # tables: venues, events, venue_blocks, audit_log, notifications

# cems/repository.py  (M1)
list_venues(conn) -> list[Venue];  get_venue(conn, venue_id) -> Venue|None
list_events(conn, status=None, organiser=None) -> list[Event];  get_event(conn, event_id) -> Event|None
insert_event(conn, event) -> int;  update_status(conn, event_id, status, reason=None) -> None
find_overlapping_events(conn, venue_id, start, end) -> list[Event]       # active statuses only
find_overlapping_blocks(conn, venue_id, start, end) -> list[VenueBlock]
insert_block(conn, block) -> int;  list_blocks(conn, venue_id=None) -> list[VenueBlock]
log_action(conn, event_id, action, actor, detail="") -> None

# cems/rules.py  (M2)
validate_request(conn, title, venue_id, start, end, attendees) -> list[str]   # [] means valid
can_cancel(event, actor_name, actor_role) -> list[str]

# cems/services.py  (M3)
class BookingError(Exception): reasons: list[str]
submit_request(conn, title, event_type, organiser, venue_id, start, end, attendees) -> int
approve_request(conn, event_id, actor) -> None
reject_request(conn, event_id, actor, reason) -> None
cancel_event(conn, event_id, actor, actor_role) -> None

# cems/venue_service.py  (M1)
add_block(conn, venue_id, start, end, reason) -> int    # raises BookingError if active events overlap
```

**Target layout**
```
app.py                 # Streamlit entry: role selector + routing
cems/ __init__.py models.py db.py seed.py repository.py rules.py services.py venue_service.py notifications.py
ui/   __init__.py requester.py reviewer.py facilities.py schedule.py
tests/ conftest.py test_seed.py test_rules.py test_conflicts.py test_lifecycle.py test_notifications.py
docs/ ASSUMPTIONS.md PITCH.md contributions/m1.md … m7.md
README.md requirements.txt .gitignore
```

---

## 4. Git workflow (read this before the first commit)

1. **Everyone commits from their own machine with their own git identity.** That is what makes GitHub attribute the commit to them. If two people share a laptop, use:
   `git commit --author="Full Name <github-email>" -m "..."`
2. Work on `main`. Before **every** commit:
   ```
   git pull --rebase
   pytest -q            # from Round 1 onward; do not push a red suite
   git add <your files only>
   git commit -m "<type>(<area>): <message>"
   git push
   ```
3. **Baton rule:** commits go in round-robin order M1 → M7. Post "pushed #N" in the team chat so the next person knows it is their turn. If the next person is not ready, any other member who is ready may go first, **as long as they are not the author of the previous commit**. Then restore the order.
4. Prefer touching only your own files. Where a commit has to edit someone else's file (for example a hook in `services.py`), keep the edit to a few lines and tell the owner.
5. Commit message types: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`.

---

## 5. Commit plan: 6 rounds × 7 commits

Each row is **one commit**. "Check" says how the author validates the change before pushing.

### Round 1: Foundation (≈ min 5–20)

| # | Who | Files | Change | Commit message | Check |
|---|---|---|---|---|---|
| 1 | M1 | `.gitignore`, `requirements.txt`, `cems/__init__.py`, `ui/__init__.py`, `tests/__init__.py` | Project scaffold. requirements: `streamlit`, `pytest`. Ignore `*.db`, `__pycache__`, `.venv` | `chore: scaffold project structure and dependencies` | `pip install -r requirements.txt` works |
| 2 | M2 | `cems/models.py` | `Status` enum, `ACTIVE_STATUSES`, `Venue`, `Event`, `VenueBlock` dataclasses | `feat(models): add domain models and event status enum` | `python -c "import cems.models"` |
| 3 | M3 | `cems/db.py` | `get_conn`, `init_db` with tables `venues`, `events`, `venue_blocks`, `audit_log` | `feat(db): add SQLite schema and connection helper` | create an in-memory DB and list the tables |
| 4 | M4 | `cems/seed.py` | `seed(conn)` (idempotent). Inserts the 5 venues, Seminar Hall A confirmed 4 Aug 10–12, Innovation Lab confirmed 6 Aug 14–17, Conference Room C renovation block 4 Aug 09–18 | `feat(seed): load initial campus venues, events and blocks` | run it twice; still exactly 5 venues |
| 5 | M5 | `app.py` | Streamlit page config. Sidebar role selector (Requester / Reviewer / Facilities Manager / Schedule). Calls `init_db` + `seed` on startup. Placeholder content per role | `feat(app): add Streamlit entry point with role navigation` | `streamlit run app.py` opens |
| 6 | M6 | `tests/conftest.py`, `tests/test_seed.py` | `conn` fixture: in-memory DB, `init_db` + `seed`. Tests: 5 venues seeded, 2 confirmed events, 1 block | `test: add DB fixture and seed data tests` | `pytest -q` green |
| 7 | M7 | `README.md`, `docs/ASSUMPTIONS.md` | README: overview, prerequisites, setup, run, test commands. ASSUMPTIONS.md: assumptions 1–8 from §2 | `docs: add README run instructions and initial assumptions` | someone else follows the README successfully |

### Round 2: First vertical slice: submit a request (≈ min 20–38)

| # | Who | Files | Change | Commit message | Check |
|---|---|---|---|---|---|
| 8 | M1 | `cems/repository.py` | `list_venues`, `get_venue`, `list_events`, `get_event`, `insert_event`, `update_status`, `list_blocks`, `log_action` (row ↔ dataclass mapping) | `feat(repo): add data access functions for venues and events` | quick test in REPL |
| 9 | M2 | `cems/rules.py` | `validate_request` with these checks: title not empty, venue exists, `end > start`, duration ≤ 12 h, attendees > 0, attendees ≤ capacity. Each failure returns a clear message, e.g. "Seminar Hall A holds 120; you requested 150" | `feat(rules): validate time window, duration and capacity` | manual calls |
| 10 | M3 | `cems/services.py` | `BookingError`, `submit_request`: validate, insert as `PENDING`, write to the audit log, return the id. Raise `BookingError(reasons)` on failure | `feat(services): submit event request as PENDING after validation` | REPL: valid → id; invalid → reasons |
| 11 | M4 | `ui/requester.py`, wire in `app.py` | Request form: title, type, organiser, venue (dropdown showing capacity), date, start and end time, attendees. On submit, call the service and show success or the list of errors | `feat(ui): add event request form for requesters` | submit one request in the browser |
| 12 | M5 | `ui/reviewer.py`, wire in `app.py` | Reviewer page: table of `PENDING` requests (title, venue, time, attendees, organiser). Read-only for now | `feat(ui): add reviewer queue of pending requests` | request from #11 appears |
| 13 | M6 | `tests/test_rules.py` | Tests: end before start, zero duration, more than 12 h, capacity exceeded (150 people in Seminar Hall A), unknown venue, valid request passes | `test(rules): cover time window and capacity validations` | `pytest -q` green |
| 14 | M7 | `README.md` | Sections: Stakeholders & personas, workflows, state diagram (Mermaid), mapping of conditions 1–10 (table from §2) | `docs: document stakeholders, workflows and event state machine` | renders on GitHub |

### Round 3: Conflicts + review decisions (≈ min 38–55)

| # | Who | Files | Change | Commit message | Check |
|---|---|---|---|---|---|
| 15 | M1 | `cems/repository.py` | `find_overlapping_events` (SQL: `venue_id=? AND status IN ('PENDING','CONFIRMED') AND start < :end AND :start < end`), `find_overlapping_blocks` | `feat(repo): query overlapping active events and venue blocks` | Seminar Hall A 4 Aug 11:00–13:00 → returns 1 |
| 16 | M2 | `cems/rules.py` | Add conflict and block checks to `validate_request`, with clear messages: "Seminar Hall A is already booked 10:00–12:00 for '…' (CONFIRMED)" / "Conference Room C unavailable 09:00–18:00: renovation" | `feat(rules): reject overlapping bookings and blocked venues` | manual calls |
| 17 | M3 | `cems/services.py` | `approve_request` and `reject_request(reason)`. Guard: only `PENDING` can change; a reject reason is required. Approve re-runs the conflict check defensively. Both write to the audit log | `feat(services): add approve and reject transitions with guards` | REPL |
| 18 | M4 | `ui/requester.py` | **Pre-submit availability check** (condition 3): when venue, date or time change, call `validate_request` and show the problems live. The submit button stays disabled while there are problems | `feat(ui): show live conflict check and block invalid submissions` | choose Seminar Hall A 4 Aug 10–12 → button disabled with reason |
| 19 | M5 | `ui/reviewer.py` | Approve button and Reject button (with a required reason input) for each pending request. Show success or error and refresh | `feat(ui): let reviewers approve or reject pending requests` | approve in browser → leaves the queue |
| 20 | M6 | `tests/test_conflicts.py` | Overlap with seed confirmed event fails; back-to-back 12:00–14:00 passes; renovation block fails; a `PENDING` request also blocks the slot; a different venue at the same time passes | `test(conflicts): cover overlap, adjacency, pending holds and blocks` | `pytest -q` green |
| 21 | M7 | `docs/ASSUMPTIONS.md` | Add "Business rules" (each rule → function that enforces it) and "Scope prioritised / excluded" (partial and split bookings, suggestions, auth, recurring events, editing requests) | `docs: map business rules to code and record scope decisions` | review with M2 |

### Round 4: Cancellation, facilities, visibility (≈ min 55–70)

| # | Who | Files | Change | Commit message | Check |
|---|---|---|---|---|---|
| 22 | M1 | `cems/venue_service.py`, `cems/repository.py` (`insert_block`) | `add_block`: validates `end > start` and refuses when active events overlap, listing them (assumption 5) | `feat(venues): add maintenance blocks with active-booking guard` | REPL |
| 23 | M2 | `cems/rules.py` | `can_cancel(event, actor_name, actor_role)`: only `CONFIRMED`; actor is the organiser or has the Reviewer role | `feat(rules): define who can cancel a confirmed event` | manual calls |
| 24 | M3 | `cems/services.py` | `cancel_event`: uses `can_cancel`, sets `CANCELLED`, writes to the audit log. This releases the venue | `feat(services): cancel confirmed events and release venue` | cancel → same slot bookable again |
| 25 | M4 | `ui/requester.py` | "My Requests" tab: filter by organiser name, colored status badges, rejection reason shown, Cancel button on `CONFIRMED` events | `feat(ui): add My Requests view with status and cancellation` | cancel in browser |
| 26 | M5 | `ui/facilities.py`, wire in `app.py` | Facilities page: venue list (type, capacity), add-block form (reason dropdown: maintenance / renovation / other), list of existing blocks, error shown when refused | `feat(ui): add facilities page to manage venue blocks` | block a free slot; block over a booking is refused |
| 27 | M6 | `tests/test_lifecycle.py` | **E2E:** submit → approve → cancel → the same slot is submitted again successfully. Submit → reject → another organiser books the slot. Invalid transitions: approve after reject, cancel a pending request, approve twice. Block over a confirmed event is refused | `test(lifecycle): end-to-end request, review and cancellation flows` | `pytest -q` green |
| 28 | M7 | `ui/schedule.py`, wire in `app.py` | Schedule view for everyone: pick a date and see each venue's bookings (with status) and blocks. Visibility is one of the pain points in the brief | `feat(ui): add daily venue schedule view for all users` | 4 Aug shows Seminar Hall A booking and Conference Room C block |

### Round 5: Bonus + hardening (≈ min 70–82)

**Bonus feature: in-app notifications.** Requesters get notified when their request is approved, rejected (with the reason) or cancelled. This addresses the brief's pain point of "limited visibility into request status".

| # | Who | Files | Change | Commit message | Check |
|---|---|---|---|---|---|
| 29 | M1 | `cems/notifications.py`, `cems/db.py` | `notifications` table; `notify(conn, recipient, message)`, `list_for(conn, recipient)`, `mark_read` | `feat(notify): add notification store` | REPL |
| 30 | M2 | `cems/services.py` (3 small hooks) | Call `notify` from approve, reject and cancel, with meaningful messages | `feat(notify): notify organisers on approve, reject and cancel` | REPL |
| 31 | M3 | `cems/services.py` | Hardening: wrap submit and approve in one transaction (`BEGIN IMMEDIATE`) so the check and the insert are atomic. Add `get_history(event_id)` from the audit log | `fix(services): make conflict check and write atomic; expose history` | `pytest -q` green |
| 32 | M4 | `ui/requester.py` | Notifications inbox for the organiser (unread count badge, mark as read) | `feat(ui): add requester notification inbox` | approve as reviewer → inbox shows it |
| 33 | M5 | `ui/reviewer.py`, `app.py` | Polish: show the audit history of each request; consistent `st.error` / `st.success` messages; seed reset button for demos | `feat(ui): show request history and add demo reset` | full click-through |
| 34 | M6 | `tests/test_notifications.py` | Notifications created on approve, reject and cancel; none on a failed submit | `test(notify): verify notifications across lifecycle events` | `pytest -q` green |
| 35 | M7 | `docs/PITCH.md` | Two slides. **Slide 1:** problem, personas, workflows, rules, assumptions, scope. **Slide 2:** architecture (UI → services → rules → repository → SQLite), decisions, trade-offs, testing, limitations, next steps | `docs: add two-slide consulting pitch` | team review |

### Round 6: Ownership notes + release (≈ min 82–88)

Each member writes **their own file**, so there are no merge conflicts. Each file answers the evaluator's questions: *my contribution · one business rule · one part of the solution · one assumption or trade-off · how I validated it.*

| # | Who | Files | Commit message |
|---|---|---|---|
| 36 | M1 | `docs/contributions/m1.md` | `docs: add M1 contribution notes (persistence and overlap query)` |
| 37 | M2 | `docs/contributions/m2.md` | `docs: add M2 contribution notes (validation rules)` |
| 38 | M3 | `docs/contributions/m3.md` | `docs: add M3 contribution notes (state machine and atomicity)` |
| 39 | M4 | `docs/contributions/m4.md` | `docs: add M4 contribution notes (requester UX and pre-check)` |
| 40 | M5 | `docs/contributions/m5.md` | `docs: add M5 contribution notes (reviewer and facilities UI)` |
| 41 | M6 | `docs/contributions/m6.md` + `README.md` "Testing" section with the `pytest` output | `docs: add test strategy, results and M6 notes` |
| 42 | M7 | `docs/contributions/m7.md` + `README.md` final sections: trade-offs, known limitations, next steps, links to the pitch and contributions | `docs: finalize README with trade-offs, limitations and next steps` |

**Contributions are equal: 6 commits each.** Each member has 3–4 code or test commits and 1–2 docs commits, and owns one demo-able area.

---

## 6. Demo script (≈ 5 min, rehearse at min 85–90)

1. **M7:** problem, personas, rules (Slide 1).
2. **M4 → M5:** *Happy path.* As a Requester, book Main Auditorium on 5 Aug 2026, 14:00–16:00, 300 attendees. The request is `PENDING`. As the Reviewer, approve it: it is now `CONFIRMED`. The requester's inbox shows the notification.
3. **M4:** *Conflict.* Seminar Hall A, 4 Aug 2026, 11:00–13:00 → blocked before submit with the reason. Conference Room C on 4 Aug → renovation message. Innovation Lab with 80 attendees → capacity message.
4. **M5 → M4:** *Release.* Reject a pending request; the same slot is now bookable. Cancel a confirmed event; the slot is released (show it in the schedule view).
5. **M1:** Facilities Manager adds a maintenance block. A block over a confirmed event is refused.
6. **M6:** run `pytest -q` live and walk through the test categories.
7. **M2 / M3:** design decisions: layered architecture, the overlap formula, the state guards, atomic check and insert.
8. **M7:** Slide 2: trade-offs, limitations, next steps.

**Known limitations to state openly:** no real authentication (the role selector is trusted); single-user SQLite; no recurring events; no editing of requests (by design, per condition 6); no time zones; no email delivery (notifications are in-app only).

**Next steps:** SSO login, email or calendar (.ics) integration, utilisation analytics, alternative-venue suggestions, recurring bookings, approval SLAs.

---

## 7. AI usage guidance (20% of the score)

- Give Copilot or Claude **the interface contract in §3** so generated code matches the agreed signatures.
- Every member **reviews and runs** the AI output before committing. Note in your contribution file one AI suggestion you rejected or corrected (for example, an overlap check using `<=`, which wrongly blocks back-to-back bookings).
- M6 asks the AI to *propose edge cases*, then keeps only the ones that match the documented assumptions.
