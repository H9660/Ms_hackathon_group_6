# Test Scenarios

These are the end-to-end scenarios used for the final validation and the demo. Each one is automated in [`tests/test_acceptance.py`](../tests/test_acceptance.py), which clicks through the real Streamlit app (headless `AppTest`) in one session, switching roles in the sidebar like a presenter. Every run starts from the initial campus data.

**Final run:** `pytest -q` on the Step 7 build → **182 passed** (S1–S12 all pass).

| ID | Scenario | Steps | Expected result | Result |
|---|---|---|---|---|
| S1 | **Happy path, end to end** | Requester books Main Auditorium, 5 Aug 2026, 14:00–16:00, 300 attendees → Submit. Reviewer → Approve. Requester → Inbox | PENDING → CONFIRMED; requester's inbox shows "was approved" | ✅ Pass |
| S2 | Overlap blocked before submit | Seminar Hall A, 4 Aug, 11:00–13:00 | Submit disabled; "already booked 04 Aug 2026 10:00–12:00" | ✅ Pass |
| S3 | Renovation block | Conference Room C, 4 Aug, 14:00–15:00 | Submit disabled; "(Renovation)" | ✅ Pass |
| S4 | Capacity exceeded | Innovation Lab, 80 attendees | Submit disabled; "holds 60 people" | ✅ Pass |
| S5 | Invalid time window | End 14:00 before start 16:00 | Submit disabled; "End time must be after the start time." | ✅ Pass |
| S6 | Back-to-back allowed | Seminar Hall A, 4 Aug, 12:00–14:00 (seeded event ends 12:00) | Submit enabled | ✅ Pass |
| S7 | Reject releases the slot | Submit S1's request → Reviewer rejects with a reason → Drama Club requests the same slot | Second request can be submitted | ✅ Pass |
| S8 | Cancel releases the slot | AI Club cancels its seeded Seminar Hall A event → requests 4 Aug 10:00–12:00 again | Event CANCELLED; slot bookable | ✅ Pass |
| S9 | Block over a booking refused | Facilities blocks Innovation Lab on 6 Aug (seeded confirmed event) | "Cannot block Innovation Lab…" with the booking listed | ✅ Pass |
| S10 | Removing a block reopens the venue | Facilities removes the Conference Room C renovation → Requester books it on 4 Aug | Submit enabled | ✅ Pass |
| S11 | Campus schedule | Open *Campus schedule* for 4 Aug | 1 CONFIRMED + 1 BLOCKED; Main Auditorium listed as free all day | ✅ Pass |
| S12 | Demo reset | Submit a request → Reset demo data | Back to 2 confirmed events; notifications cleared | ✅ Pass |

## Coverage by layer

| Layer | Test files | Tests |
|---|---|---|
| Models & DB constraints | `test_models.py`, `test_db.py` | 15 |
| Seed data vs. brief | `test_seed.py` | 9 |
| Repository & overlap SQL | `test_repository.py`, `test_overlap.py` | 28 |
| Business rules | `test_rules.py` | 38 |
| Lifecycle / state machine | `test_lifecycle.py` | 25 |
| Venue blocks | `test_blocks.py` | 14 |
| Notifications (bonus) | `test_notifications.py` | 13 |
| UI pages (AppTest) | `test_app_requester.py`, `test_app_reviewer_facilities.py`, `test_app_inbox.py` | 26 |
| Acceptance scenarios + schedule | `test_acceptance.py` | 14 |
| **Total** | | **182** |

## Extra checks done during development

- **Mutation check (Step 2):** changing the overlap SQL from `<` to `<=` made 3 tests fail. The boundary tests do catch the classic back-to-back bug.
- **Concurrency (Step 3):** with a second connection holding the write lock, `submit_request` waited and then failed with "database is locked" and wrote nothing. Once the lock was released, it succeeded.
- **Real server (Step 4):** `streamlit run app.py` started headless; `/_stcore/health` returned `ok`, and the page returned HTTP 200.
- **Rollback:** tests inject failures part-way, in the audit log (Step 3) and the notification store (Step 6), and check that the whole transition rolls back.
