# Assumptions and Business Rules

The brief allows teams to add assumptions as long as they are documented and applied consistently. This file lists ours and points to the code that enforces each rule.

## Assumptions

| # | Assumption | Why | Enforced in |
|---|---|---|---|
| A1 | Time intervals are **half-open** `[start, end)`. Two bookings overlap only if `new.start < old.end AND old.start < new.end`. Back-to-back bookings (one ends at 12:00, the next starts at 12:00) are allowed. | Normal room-booking practice; avoids leaving gaps between events. | `repository.find_overlapping_events`, `find_overlapping_blocks` |
| A2 | Expected attendees must be between 1 and the venue capacity (inclusive). | The brief lists "venues selected without considering capacity" as a pain point. | `rules.validate_capacity` |
| A3 | `end > start`, and an event lasts at most **12 hours**. Multi-day events are out of scope. | Catches input mistakes (e.g. AM/PM swaps). Long festivals can be booked as several requests. | `rules.validate_time_window` |
| A4 | Requests for past dates are **not** rejected against the real clock. | The initial campus data is in Aug 2026. Rejecting past dates would make the brief's scenarios impossible to demo. | (no check, deliberately) |
| A5 | A maintenance block cannot be placed over an active booking. The event must be cancelled first. | Keeps condition 2 true: a venue is never both booked and blocked. | `venue_service.add_block` |
| A6 | No authentication. The acting role and name are chosen in the UI. | Prioritised the workflow over login within 90 minutes; the brief marks authentication as optional. | `models.Role`, UI sidebar |
| A7 | Only `PENDING` requests can be approved or rejected. Only `CONFIRMED` events can be cancelled. A pending request cannot be withdrawn. | Keeps the state machine small and explainable. | `rules.can_cancel`, `services` (Step 3) |
| A8 | Times are stored with **minute precision** and no time zone. | Single-campus system; ISO text keeps the SQL simple. | `models.to_db` / `from_db` |
| A9 | Organiser names are compared **case- and whitespace-insensitively** when deciding who may cancel. | With no login, small typing differences should not lock an organiser out of their own event. | `rules.can_cancel` |
| A10 | Event type must be one of: Workshop, Hackathon, Placement, Club, Cultural, Competition. | These are the event kinds the brief lists. | `models.EVENT_TYPES`, `rules.validate_request` |
| A11 | Every problem with a request is reported at once. A check that depends on another is skipped when that check fails: no capacity check without a venue, and no availability check without a valid time window. | The requester can fix everything in one go, without misleading follow-on messages. | `rules.validate_request` |
| A12 | Approval **re-checks availability**, excluding the request itself, and refuses if the slot is no longer free. | Defence in depth. The submit-time checks should already guarantee this, but approval is where a booking becomes binding. | `services.approve_request` |
| A13 | Every transition requires the acting person's **name**. Rejection also requires a **reason**. | Gives an accountable audit trail, and the requester learns why a request was rejected. | `services._require_actor`, `reject_request` |
| A14 | Records are **never deleted**. Rejecting or cancelling only changes the status. | Keeps the history and audit log intact. | `services`, `repository.update_status` |
| A15 | In the UI an event takes place on **a single date**: start and end time are on the chosen day. | Fits the 12-hour maximum (A3) and keeps the form simple. | `ui/requester.py` |
| A16 | The requester's **organiser name is the name entered in the sidebar**. "My requests" and cancel rights use that name. | Follows from having no login (A6). | `app.py`, `ui/requester.py` |
| A17 | The request form opens on **4 Aug 2026**. | That is the date of the initial campus data, so demo scenarios are one click away. | `ui/requester.DEFAULT_DATE` |
| A18 | Venue blocks may **span several days** and have no 12-hour limit. | Renovations take days. The 12-hour limit (A3) applies only to events. | `venue_service.add_block` |
| A19 | Facilities can **remove a block** (e.g. work finished early). The period immediately becomes bookable. | The brief notes venues "remaining unavailable" as a pain point. | `venue_service.remove_block` |
| A20 | The Reviewer page **disables Approve** when the slot is no longer available, and shows why. The service enforces the same check. | Reviewers see the problem before they click. | `ui/reviewer.py`, `services.approve_request` |
| A21 | Reviewers share **one role inbox** ("Reviewer"). Organisers get a personal inbox keyed by their name, matched case-insensitively. | No user accounts (A6). A shared queue suits a small Events Office. | `notifications.REVIEWER_INBOX`, `COLLATE NOCASE` |
| A22 | Notifications are **in-app only**: no email or SMS. | The brief rules out external services. | `cems/notifications.py` |
| A23 | Notifications are written **in the same transaction** as the change they describe. | No notification for a change that was rolled back, and no change without its notification. | `services.*` |

## Brief conditions → implementation

| # | Condition | Rule / code |
|---|---|---|
| 1 | Event has start, end and venue | `rules.validate_time_window`, venue existence check; DB `CHECK (end_at > start_at)` |
| 2 | No overlapping active or confirmed bookings | `rules.check_availability` → `repository.find_overlapping_events` (only PENDING and CONFIRMED count) |
| 3 | Conflict prevented before submit | `ui/requester.py` re-runs `validate_request` on every change and disables Submit while problems exist. `services.submit_request` re-validates inside the transaction |
| 4 | Maintenance or renovation unavailability | `rules.check_availability` → `repository.find_overlapping_blocks` |
| 5 | Review before confirmation | `services.approve_request` re-checks with `check_availability(..., exclude_event_id=...)` (Step 3) |
| 6 | Reject closes the request and releases the venue | status `REJECTED` is not in `ACTIVE_STATUSES`; there is no edit path |
| 7 | Appropriate user can cancel | `rules.can_cancel`: the organiser or a Reviewer, confirmed events only |
| 8 | Cancel releases the venue | status `CANCELLED` is not in `ACTIVE_STATUSES` |
| 9 | No partial or split bookings, no suggestions | out of scope |
| 10 | Clear reason when a request can't proceed | every rule returns readable messages naming the venue, times and cause |

## Example messages

| Situation | Message |
|---|---|
| Overlap | `Seminar Hall A is already booked 04 Aug 2026 10:00–12:00 for 'Intro to Machine Learning Workshop' (CONFIRMED).` |
| Block | `Conference Room C is unavailable 04 Aug 2026 09:00–18:00 (Renovation).` |
| Capacity | `Innovation Lab holds 60 people; 80 expected attendees exceed its capacity.` |
| Cancel not allowed | `Only the organiser (AI Club) or a Reviewer can cancel this event.` |
