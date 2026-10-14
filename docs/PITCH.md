# Consulting Pitch: Campus Event Management System

---

## Slide 1: Problem Understanding

**The problem.** Campus events are coordinated through messages and spreadsheets. As volume grows, this leads to:
- double-booked venues;
- venues chosen without checking capacity;
- no visibility of request status;
- slow reviews;
- venues "stuck" after cancellations or maintenance.

**Stakeholders / personas**

| Persona | Needs |
|---|---|
| **Requester** (club, faculty, placement cell) | Book a suitable venue fast; know the outcome |
| **Event Reviewer** (Events Office) | A clear queue; approve or reject with confidence |
| **Facilities Manager** | Take venues offline for maintenance or renovation |
| **Campus community** | See what's happening where, and when |

**Workflows we prioritised**
- **Request → Review → Confirm or Reject → Cancel.** This is the full lifecycle, with every transition guarded.
- **Venue blocking** for maintenance or renovation.
- **Campus-wide schedule.**

**Business rules we found**
- A venue holds **only PENDING and CONFIRMED** bookings. Rejecting or cancelling releases it.
- Two bookings overlap when one **starts before the other ends** (`new.start < old.end` and `old.start < new.end`). Back-to-back bookings are allowed.
- Conflicts, blocks, capacity and bad times are caught **before submit**, and each comes with a clear reason.
- **Review is mandatory.** A rejected request is closed, and a revision means a new request.
- **Only the organiser or the Events Office** can cancel. **A block can't cover an active booking.**

**Key assumptions** (24 in total, see `ASSUMPTIONS.md`)
- No login: a role selector stands in for it.
- Events last at most 12 hours, on a single day.
- Past dates are allowed, because the brief's data is in Aug 2026.

**Scope for 90 minutes:** one reliable end-to-end flow, the conflict and failure handling, three role views, and one bonus feature (notifications).

---

## Slide 2: Solution & Engineering Decisions

**Approach.** Python, Streamlit and SQLite, all running locally. Strict layers:
`UI → services (state machine) → rules (validation) → repository (SQL) → SQLite`

**Design decisions**
1. **Rules only read, and return readable reasons.** The same checks power the live form check, the service's re-check, and the reviewer's warning.
2. **Each change is one all-or-nothing transaction** (`BEGIN IMMEDIATE`). The database is locked for writing before the checks run, so two people can't book the same slot at once. The check, the write, the history entry and the notification all happen together, or none do.
3. **Releasing a venue is just a status change.** Nothing is deleted, so the full history survives.
4. **The database also enforces the basics** (`CHECK` and foreign-key constraints) as a last line of defence.
5. **Bonus:** in-app notifications for reviewers (new requests) and organisers (outcomes, with reasons).

**Trade-offs**
- No authentication, in exchange for a complete, demonstrable lifecycle.
- Reviewers share one inbox: simple, but reading it marks it read for everyone.
- SQLite runs one write at a time. That's fine for one campus, but it isn't built for heavy concurrent use.

**Testing and validation:** 182 automated tests.
- Business rules, overlap boundaries and every invalid status change.
- 26 UI tests plus 12 acceptance scenarios that click through the real app.
- A mutation check on the overlap query, a two-connection concurrency check, and rollback tests.

**Known limitations**
- No real identity.
- No recurring or multi-day events.
- No email or calendar integration.
- Blocks have no history.
- No time zones.

**Next steps**
- SSO login with per-person reviewer inboxes.
- Email and `.ics` calendar export.
- Recurring bookings.
- Utilisation analytics.
- Alternative-venue suggestions.
- Approval targets and escalation.
