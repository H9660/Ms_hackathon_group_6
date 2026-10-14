# Campus Event Management System: Team Plan (7 members, 90 min)

**Stack:** Python 3.10+, Streamlit (UI), SQLite (stdlib `sqlite3`), pytest.

**Process: 7 incremental steps, one member per step, one commit per step.**
M1 builds Step 1 and pushes. M2 pulls, builds Step 2 on top, and pushes. Then M3, and so on up to M7.
Each step leaves the project **working and tested**, and each step builds visibly on the previous one.

```
M1 ──push──▶ M2 ──push──▶ M3 ──push──▶ M4 ──push──▶ M5 ──push──▶ M6 ──push──▶ M7 ──push──▶ demo
Foundation   Rules        Workflow     Requester UI Reviewer +   Bonus:       Schedule +
                                                    Facilities   Notify       Docs/Pitch
```

---

## 1. How 7 people stay busy while only one is committing

The commits happen one after another, but **the work happens in parallel**:

| Phase | What everyone does |
|---|---|
| **Kickoff (min 0–8)** | All 7 agree on §2 (problem, rules, assumptions) and §3 (interface contract). Everyone pastes the contract into their own Copilot or Claude session. |
| **Draft ahead** | While earlier steps are being built, each member drafts **their own step's code** on their machine against the agreed contract. Do not commit it yet. |
| **Your turn** | `git pull`, run the previous step (validate it), merge in your draft, finish it, test, commit, push, announce. |
| **After your turn** | Review the next steps as they land: pull, run `pytest -q` and the app, and report problems to the author before they hand over. |

**Each step owns its own files** (listed below), so the drafts merge into the codebase without conflicts.

**Target timing:** ≈ 11 minutes per step.

| Step | Owner | Window (min) |
|---|---|---|
| 1 | M1 | 8–19 |
| 2 | M2 | 19–30 |
| 3 | M3 | 30–41 |
| 4 | M4 | 41–52 |
| 5 | M5 | 52–63 |
| 6 | M6 | 63–74 |
| 7 | M7 | 74–85 |
| Demo rehearsal | all | 85–90 |

If a step runs late, its owner trims scope (see "If short on time" in each step). The handover must not slip.

---

## 2. Problem understanding (agree in kickoff)

**Personas**
- **Requester:** a club, faculty member or placement cell organiser who requests venues.
- **Event Reviewer:** the Student Affairs / Events Office. Approves or rejects requests.
- **Facilities Manager:** blocks venues for maintenance or renovation.
- **Campus community:** views the venue schedule.

**Event lifecycle**
```
 submit (all checks pass)
 ──────────────▶ PENDING ──approve──▶ CONFIRMED ──cancel──▶ CANCELLED
                    └──reject(reason)──▶ REJECTED (closed; revisions need a new request)
```
- **Active statuses** (these hold the venue): `PENDING`, `CONFIRMED`.
- **Released statuses** (these free the venue): `REJECTED`, `CANCELLED`. Releasing needs no extra code: the overlap query only counts active statuses.

**How the brief's conditions map to code**

| # | Condition | Enforced in (step) |
|---|---|---|
| 1 | Start, end and venue | `models.Event`, `rules` (S1, S2) |
| 2 | No overlap with active or confirmed bookings | `repository.find_overlapping_events` + `rules` (S2) |
| 3 | Conflict prevented before submit | live pre-check in the request form (S4); the service re-validates (S3) |
| 4 | Maintenance or renovation blocks | `venue_blocks` + `rules` (S2), facilities page (S5) |
| 5 | Review before confirmation | `approve_request` (S3), reviewer page (S5) |
| 6 | Reject closes the request and releases the venue | `reject_request` (S3); there is no edit path |
| 7 | Appropriate user cancels | `rules.can_cancel`: the organiser or the Reviewer (S2, S3) |
| 8 | Cancel releases the venue | status becomes `CANCELLED` (S3) |
| 9 | No partial or split bookings, no suggestions | out of scope (S7 docs) |
| 10 | Clear reason when a request can't proceed | `validate_request` returns readable messages (S2) |

**Assumptions** (everyone applies them the same way)
1. Overlap means `new.start < old.end AND old.start < new.end`. Back-to-back bookings (12:00 end, 12:00 start) are **allowed**.
2. Attendees must be no more than the venue capacity. Attendees must be more than 0.
3. `end > start`, and the maximum duration is 12 hours.
4. Past dates are **not** rejected against the real clock. The seed data is in Aug 2026, so this rule would break the demo.
5. A maintenance block cannot be placed over an active booking. The event must be cancelled first.
6. No authentication. A role selector in the sidebar stands in for login, and this trade-off is documented.
7. Only `PENDING` requests can be approved or rejected. Only `CONFIRMED` events can be cancelled.
8. Datetimes are stored as ISO strings `YYYY-MM-DDTHH:MM`, which sort chronologically.

---

## 3. Interface contract (frozen at kickoff; everyone drafts against it)

```python
# cems/models.py                                   (Step 1)
class Status(str, Enum): PENDING, CONFIRMED, REJECTED, CANCELLED
ACTIVE_STATUSES = (Status.PENDING, Status.CONFIRMED)
EVENT_TYPES = ["Workshop", "Hackathon", "Placement", "Club", "Cultural", "Competition"]
@dataclass Venue(id, name, type, capacity)
@dataclass Event(id, title, event_type, organiser, venue_id, start, end, attendees, status, reject_reason=None)
@dataclass VenueBlock(id, venue_id, start, end, reason)

# cems/db.py + cems/seed.py                        (Step 1)
get_conn(path="cems.db") -> Connection;  init_db(conn);  seed(conn);  reset_db(conn)

# cems/repository.py                               (Step 1; overlap queries added in Step 2)
list_venues, get_venue, list_events(status=None, organiser=None), get_event,
insert_event -> id, update_status(event_id, status, reason=None), list_blocks(venue_id=None),
insert_block -> id, log_action(event_id, action, actor, detail=""), get_history(event_id)
find_overlapping_events(conn, venue_id, start, end, exclude_event_id=None) -> list[Event]  # active only (Step 2)
find_overlapping_blocks(conn, venue_id, start, end) -> list[VenueBlock]  # (Step 2)

# cems/rules.py                                    (Step 2)
validate_request(conn, title, organiser, event_type, venue_id, start, end, attendees) -> list[str]
can_cancel(event, actor_name, actor_role) -> list[str]
check_availability(conn, venue, start, end, exclude_event_id=None) -> list[str]   # overlap + blocks; Step 3 approve re-check
# models.Role: REQUESTER="Requester", REVIEWER="Reviewer", FACILITIES="Facilities Manager"   (added in Step 2)

# cems/services.py                                 (Step 3)
class BookingError(Exception): reasons: list[str]
submit_request(...) -> int;  approve_request(conn, event_id, actor)
reject_request(conn, event_id, actor, reason);  cancel_event(conn, event_id, actor, actor_role)

# cems/venue_service.py                            (Step 5)
add_block(conn, venue_id, start, end, reason) -> int    # BookingError if active events overlap
remove_block(conn, block_id) -> None                    # added in Step 5

# cems/notifications.py                            (Step 6)
notify(conn, recipient, message);  list_for(conn, recipient);  unread_count(conn, recipient);  mark_read(conn, id)
```

---

## 4. Git routine (every step)

```
git pull --rebase
pytest -q && streamlit run app.py      # validate the previous step first (from Step 4 on, app.py exists)
# ...merge in your draft, finish, test...
pytest -q                              # must be green
git add <your step's files>
git commit -m "<message from your step>"
git push                               # then announce "Step N pushed" in team chat
```
- Commit from **your own machine and git identity** so GitHub credits you. On a shared laptop, use `git commit --author="Name <github-email>"`.
- Every step includes `docs/contributions/mN.md`. It covers what you built, one business rule, one assumption or trade-off, how you validated your step **and the previous step**, and one AI suggestion you corrected.

---

## 5. The 7 steps

### Step 1 · M1 · Foundation: data model, database, seed data
**Builds:** the project skeleton and a working data layer.

| Files | Content |
|---|---|
| `.gitignore`, `requirements.txt` | `streamlit`, `pytest`; ignore `*.db`, `__pycache__`, `.venv` |
| `cems/__init__.py`, `cems/models.py` | `Status`, `ACTIVE_STATUSES`, `EVENT_TYPES`, dataclasses |
| `cems/db.py` | `get_conn`, `init_db`: tables `venues`, `events`, `venue_blocks`, `audit_log` |
| `cems/seed.py` | idempotent `seed()` with the 5 venues; Seminar Hall A CONFIRMED 4 Aug 2026 10:00–12:00; Innovation Lab CONFIRMED 6 Aug 2026 14:00–17:00; Conference Room C renovation block 4 Aug 2026 09:00–18:00. Also `reset_db()` |
| `cems/repository.py` | CRUD functions from §3 (no overlap queries yet) |
| `tests/conftest.py`, `tests/test_seed.py` | in-memory DB fixture; 5 venues, 2 confirmed events, 1 block; seeding twice doesn't duplicate |
| `README.md` | overview, prerequisites, setup and test commands |
| `docs/contributions/m1.md` | |

**Done when:** `pip install -r requirements.txt && pytest -q` passes.
**Commit:** `feat: project foundation with domain models, SQLite schema and seed data`
**If short on time:** drop `reset_db` (M5 can add it in Step 5).

### Step 2 · M2 · Business rules and conflict detection
**Builds on Step 1:** adds every validation the brief requires, each with a clear message.

| Files | Content |
|---|---|
| `cems/repository.py` (+2 functions) | `find_overlapping_events` (active only: `start < :end AND :start < end`), `find_overlapping_blocks` |
| `cems/rules.py` | `validate_request` checks: title and organiser required, event type valid, venue exists, `end > start`, ≤ 12 h, `0 < attendees ≤ capacity`, no overlapping active booking, no block. Messages such as *"Seminar Hall A is already booked 10:00–12:00 for 'X' (CONFIRMED)"*, *"Conference Room C unavailable 09:00–18:00: renovation"*, *"Innovation Lab holds 60; you requested 80"*. Also `can_cancel` |
| `tests/test_rules.py` | each rule failing; back-to-back 12:00–14:00 passes; same time at a different venue passes; `can_cancel` cases |
| `docs/ASSUMPTIONS.md` | assumptions 1–8 and the condition → code table from §2 |
| `docs/contributions/m2.md` | |

**Done when:** `pytest -q` passes, including the seed conflicts.
**Commit:** `feat(rules): add booking validations with overlap and venue-block detection`

### Step 3 · M3 · Workflow state machine
**Builds on Step 2:** turns validated input into a lifecycle with guarded transitions.

| Files | Content |
|---|---|
| `cems/services.py` | `BookingError`. `submit_request`: inside `BEGIN IMMEDIATE`, validate, insert as `PENDING`, write to the audit log. `approve_request`: only from PENDING, re-checks conflicts. `reject_request`: only from PENDING, reason required. `cancel_event`: uses `can_cancel`. Every transition writes to the audit log |
| `tests/test_lifecycle.py` | **E2E:** submit → approve → cancel → the same slot is resubmitted successfully. Submit → reject → another organiser books the slot. A PENDING request blocks the slot. Invalid transitions raise (approve after reject, cancel while pending, approve twice) |
| `README.md` (+section) | state diagram (Mermaid) and workflow description |
| `docs/contributions/m3.md` | |

**Done when:** the full lifecycle works in tests.
**Commit:** `feat(services): add request lifecycle with review, rejection and cancellation`

### Step 4 · M4 · Streamlit app and Requester experience
**Builds on Step 3:** the first runnable UI, with a working requester flow.

| Files | Content |
|---|---|
| `app.py` | page config; `init_db` + `seed` on startup; sidebar role selector (Requester / Reviewer / Facilities / Schedule) and "acting as" name; routing, with placeholders for pages that come later |
| `ui/__init__.py`, `ui/requester.py` | **New Request** tab: venue dropdown showing type and capacity, date, start and end time, attendees, title, type. **Live pre-check** (condition 3): while the form is filled in, call `validate_request` and list problems; the Submit button stays disabled while any exist. On submit, call `submit_request` and show success. **My Requests** tab: the current user's requests with status badges, the rejection reason, and a Cancel button on CONFIRMED events |
| `docs/contributions/m4.md` | include manual test results: a valid request, a seed conflict, the renovation block, capacity exceeded |

**Done when:** `streamlit run app.py` lets you submit a valid request, and an invalid one is blocked with its reasons.
**Commit:** `feat(ui): add Streamlit app with request form, live conflict check and My Requests`

### Step 5 · M5 · Reviewer and Facilities Manager
**Builds on Step 4:** completes the end-to-end lifecycle in the UI.

| Files | Content |
|---|---|
| `cems/venue_service.py` | `add_block`: validate the time window and reason; refuse when active events overlap, listing them (assumption 5) |
| `ui/reviewer.py` | queue of PENDING requests; Approve; Reject with a required reason; expandable audit history; can cancel any CONFIRMED event |
| `ui/facilities.py` | venue list; add-block form (maintenance / renovation / other); list of blocks; a refused block shows its reason |
| `app.py` (routing) | wire both pages; sidebar "Reset demo data" button |
| `tests/test_blocks.py` | a block on a free slot works; a block over a confirmed event is refused; a block over a pending request is refused; after a block, a request in that window is refused |
| `docs/contributions/m5.md` | |

**Done when:** the full flow works in the browser. Submit as Requester, approve as Reviewer, cancel as Requester, then the slot is free again.
**Commit:** `feat(ui): add reviewer approval queue and facilities venue blocking`

### Step 6 · M6 · Bonus: notifications
**Builds on Step 5:** fixes the brief's pain points of "limited visibility into request status" and "delays in reviewing".

| Files | Content |
|---|---|
| `cems/db.py` (+table), `cems/notifications.py` | `notifications` table and the functions from §3 |
| `cems/services.py` (small hooks) | notify the Reviewer on submit; notify the organiser on approve, reject (with the reason) and cancel |
| `ui/requester.py`, `ui/reviewer.py` (small additions) | inbox with an unread badge and mark as read |
| `tests/test_notifications.py` | notifications are created for each transition; none on a failed submit; `mark_read` lowers the unread count |
| `docs/contributions/m6.md` | |

**Done when:** approving as Reviewer makes a notification appear in the Requester's inbox.
**Commit:** `feat(notify): add in-app notifications for request lifecycle events`
**If short on time:** do the organiser notifications only.

### Step 7 · M7 · Schedule view, final validation and the consulting pitch
**Builds on Step 6:** visibility for the whole campus, plus the deliverables needed to submit.

| Files | Content |
|---|---|
| `ui/schedule.py`, `app.py` (routing) | pick a date and see each venue's bookings (with status) and blocks; capacity shown |
| `docs/TEST_SCENARIOS.md` | manual end-to-end scenarios run on the final build, with pass or fail recorded |
| `docs/PITCH.md` | **Slide 1:** problem, personas, workflows, rules, assumptions, scope. **Slide 2:** architecture (UI → services → rules → repository → SQLite), design decisions, trade-offs, testing, limitations, next steps |
| `README.md` (final) | scope prioritised, features excluded, trade-offs, known limitations, next steps, links to the docs |
| `docs/contributions/m7.md` | |

**Done when:** `pytest -q` passes, every scenario is recorded, and the README covers all repository deliverables.
**Commit:** `feat: add venue schedule view, test scenarios and consulting pitch`

---

## 6. Workload balance

| Member | Code | Tests | Docs | Demo segment |
|---|---|---|---|---|
| M1 | models, DB, seed, repository | seed tests | README base | data model and seed |
| M2 | rules, overlap queries | rule tests | ASSUMPTIONS | conflict rules |
| M3 | services / state machine | lifecycle E2E | state diagram | lifecycle and guards |
| M4 | app shell, requester UI | manual UI test | — | happy path and blocked submit |
| M5 | venue_service, reviewer and facilities UI | block tests | — | approve, reject, block |
| M6 | notifications (bonus) | notification tests | — | bonus feature |
| M7 | schedule view | manual scenario run | pitch, final README | Slides 1 and 2 |

Every member has **one commit** that includes code, its validation, and a contribution note.

---

## 7. Demo script (≈ 5 min)

1. **M7:** Slide 1: problem, personas, rules.
2. **M4:** *Happy path.* As a Requester, book Main Auditorium on 5 Aug 2026, 14:00–16:00, 300 attendees. The request is `PENDING`.
3. **M5:** As the Reviewer, approve it: `CONFIRMED`. **M6:** the requester's inbox shows the notification.
4. **M4 / M2:** *Conflicts.* Seminar Hall A, 4 Aug, 11:00–13:00 → overlap. Conference Room C on 4 Aug → renovation. Innovation Lab with 80 attendees → capacity. Each is blocked before submit with its reason.
5. **M3 / M5:** *Release.* Reject a request, or cancel a confirmed event. **M7:** the schedule view shows the slot free, and it can be booked again.
6. **M5:** a block over a confirmed event is refused.
7. **M1 / M6:** run `pytest -q` live and explain the data layer and test coverage.
8. **M7:** Slide 2: decisions, trade-offs, limitations, next steps.

**Limitations to state:** no real authentication; single-user SQLite; no recurring events; requests can't be edited (by design, per condition 6); no time zones; notifications are in-app only.
**Next steps:** SSO, email or `.ics` calendar export, utilisation analytics, alternative-venue suggestions, recurring bookings.

---

## 8. AI usage (20% of the score)

- Give the AI the **contract in §3** and **your step's table**, so the code it generates fits the codebase.
- Review and run everything before committing. Record one AI mistake you corrected in your contribution note (for example, an overlap check using `<=`, which wrongly blocks back-to-back bookings).
- Before pushing, ask the AI to review your diff against the rules in §2.
