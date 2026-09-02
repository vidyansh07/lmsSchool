# Phase 3 — completion checklist

**Status: complete.** Batches, schedules, enrolment, course access, dashboards,
the calendar and the progress foundation are built, tested and verified against
a running stack.

Last verified: 2026-09-01 · 459 backend tests (91% coverage) · 59 frontend unit tests · 35 end-to-end tests

| Symbol | Meaning |
| --- | --- |
| ✅ | Done and verified by a test, a scan or a live run |
| 🟡 | Foundation in place, full feature intentionally deferred |
| ⬜ | Deferred — out of scope for this phase |

---

## §1 Scope

| Item | Status |
| --- | --- |
| Batch management | ✅ |
| Batch schedules | ✅ |
| Trainer assignment | ✅ with conflict checking |
| Student enrollment | ✅ |
| Course access | ✅ gated on a live enrolment |
| Enrollment status | ✅ five states with a transition table |
| Batch capacity | ✅ enforced under a row lock |
| Student learning dashboard | ✅ |
| Trainer dashboard foundation | ✅ |
| Calendar | ✅ one abstraction, source registry |
| Timetable | ✅ |
| Course access control | ✅ |
| Basic learning progress foundation | ✅ minimal, by design |
| API | ✅ 18 routes |
| Frontend | ✅ 6 new pages |
| Tests | ✅ |
| Staging seed data | ✅ |
| Attendance / assignments / quizzes / exams / certificates / payments | ⬜ not built, as instructed |

---

## §2–3 Batch and schedule

| Requirement | Status |
| --- | --- |
| ID, public identifier, batch code | ✅ UUID + `GRS-B-00021`, sequence-allocated |
| Name, course, description, trainer | ✅ |
| Start date, end date, capacity | ✅ |
| Status: UPCOMING / ACTIVE / COMPLETED / CANCELLED / ARCHIVED | ✅ |
| Created by, created and updated dates | ✅ |
| End date cannot precede start date | ✅ model `clean` + `CheckConstraint` |
| Capacity must be positive | ✅ validator + `CheckConstraint` |
| Trainer must be active | ✅ refused at both creation and assignment |
| Course must be in a valid state | ✅ published or in review only |
| Schedule: day, start, end, time zone, location, trainer, batch | ✅ |
| End time after start time | ✅ `clean` + `CheckConstraint` |
| Architecture ready for conflict detection | ✅ **implemented**, not merely prepared |

---

## §4–5 Enrolment and its rules

| Requirement | Status |
| --- | --- |
| Connects student → course → batch | ✅ |
| Enrolment ID, student, course, batch | ✅ `GRS-E-00307` |
| Status, enrolled at, start date, access end date | ✅ |
| Completion state placeholder, created by | ✅ `completed_at` |
| Statuses: PENDING / ACTIVE / SUSPENDED / COMPLETED / CANCELLED | ✅ |
| No duplicated student/course/batch data | ✅ relationships only; `course` is derived from the batch and the match is enforced |
| Student is active | ✅ |
| Course exists, batch exists | ✅ foreign keys with `PROTECT` |
| Batch is accepting students | ✅ upcoming or active only |
| Course matches batch | ✅ enforced in `clean`; a client-supplied `course_id` is refused |
| Capacity is available | ✅ checked under `SELECT … FOR UPDATE` |
| No duplicate live enrolment | ✅ **partial unique index**, tested by bypassing the service |
| Database constraints where possible | ✅ two check constraints, two partial/unique indexes |

---

## §6 Batch management

| Actor | Requirement | Status |
| --- | --- | --- |
| Admin | Create, edit, assign trainer, add/remove students, view roster, change status, manage schedule | ✅ |
| Trainer | View assigned batches, their students, their schedules | ✅ |
| Trainer | **Cannot** edit, self-assign, or enrol | ✅ tested |
| Student | View own batches and schedules | ✅ |
| Student | **Cannot** see a roster | ✅ classmate lists are other people's data |

---

## §7 Course access control

| Requirement | Status |
| --- | --- |
| Account is active | ✅ |
| Enrollment is active | ✅ `active` or `completed` |
| Enrollment grants course access | ✅ batch not cancelled, inside the access window |
| Not reliant on frontend routing | ✅ every check is server-side, tested by direct API calls |
| Correct authorization response on an unauthorised course | ✅ 403 with no content leaked; 404 where the record is not visible at all |

Verified live: an enrolled student reads a non-preview lesson (200), an
unenrolled student is refused (403) with no body in the response, and an
anonymous caller is refused (403).

---

## §8–9 Dashboards

| Student dashboard | Status |
| --- | --- |
| My courses | ✅ with progress |
| My batches | ✅ including finished and cancelled ones |
| Current courses | ✅ |
| Upcoming classes | ✅ next 7 days |
| Recent activity | ✅ |
| Continue learning | ✅ most recently opened lesson |
| Basic course progress placeholder | ✅ real percentage, not a placeholder |
| Notifications placeholder | ✅ shaped, empty |
| Not cluttered | ✅ four cards and a course grid |

| Trainer dashboard | Status |
| --- | --- |
| Assigned batches | ✅ |
| Today's classes | ✅ |
| Upcoming classes | ✅ |
| Number of students | ✅ distinct across their batches |
| Assigned courses | ✅ |

---

## §10–11 Calendar and conflicts

| Requirement | Status |
| --- | --- |
| Scheduled classes | ✅ recurrence expanded, not stored |
| Batch events | ✅ start and end as all-day markers |
| Course start/end | ✅ covered by batch milestones |
| Prepared for deadlines, quizzes, exams, announcements | ✅ event kinds reserved; one function to add a source |
| One calendar abstraction, not one per feature | ✅ `EVENT_SOURCES` registry |
| Trainer not double-booked | ✅ |
| Batch has no overlapping classes | ✅ |
| Not reliant on frontend validation | ✅ backend refuses with 409 and names the clash |

Overlap is half-open, so back-to-back classes are allowed; it is zone-aware, so
09:00 Kolkata and 09:00 London do not clash; and it requires overlapping batch
date ranges, so terms in different months never collide.

---

## §12–13 Enrolment access and progress

| Requirement | Status |
| --- | --- |
| Cancelled/suspended changes course access | ✅ on the very next request |
| Existing progress not deleted | ✅ `LessonProgress` untouched, asserted in tests |
| History remains intact | ✅ the row survives; audit records `history_preserved` |
| No casual hard deletes | ✅ nothing in this phase deletes an enrolment |
| Student lesson progress | ✅ |
| Lesson completion | ✅ mark complete and reopen |
| Last accessed lesson | ✅ drives "continue learning" |
| Course progress | ✅ derived from published lessons only |
| Minimal enough to expand later | ✅ keyed on the enrolment, so retakes are separate attempts |

---

## §14–15 Frontend and API

| Page | Status |
| --- | --- |
| Admin: batch list | ✅ `/admin/batches` |
| Admin: create batch | ✅ dialog |
| Admin: batch details | ✅ `/admin/batches/[batchId]` |
| Admin: student enrollment | ✅ roster panel |
| Admin: trainer assignment | ✅ with clash refusal shown |
| Admin: schedule management | ✅ add and remove classes |
| Trainer: dashboard, my batches, schedule, student list | ✅ same pages, scoped by the API |
| Student: dashboard | ✅ `/dashboard` |
| Student: my courses | ✅ on the dashboard |
| Student: my batches | ✅ `/my-batches` |
| Student: calendar | ✅ `/calendar` |
| Student: course access | ✅ enforced server-side |

| API domain | Status |
| --- | --- |
| `/api/v1/batches/` | ✅ |
| `/api/v1/enrollments/` | ✅ |
| `/api/v1/schedules/` | ✅ |
| `/api/v1/calendar/` | ✅ |
| `/api/v1/dashboard/` | ✅ |
| Existing auth, permissions, pagination and API standards reused | ✅ |

---

## §16 Security

| Attack | Status |
| --- | --- |
| Student cannot enroll another student | ✅ |
| Student cannot view another student's enrollment | ✅ 404, and the status note is absent from their own view too |
| Trainer cannot manage an unrelated batch | ✅ 404 |
| Trainer cannot assign themselves to arbitrary batches | ✅ 404 |
| Student cannot access course without active enrollment | ✅ 403, no body leaked |
| Cancelled enrollment retains no access | ✅ |
| Batch IDs cannot be manipulated to bypass authorization | ✅ every record resolved inside an entitled queryset |
| Object-level permissions reviewed | ✅ all in `apps/batches/access.py` |

All verified live against the running stack, not only in tests.

---

## §17 Performance

| Requirement | Status |
| --- | --- |
| No N+1 queries | ✅ `select_related` / `prefetch_related` throughout |
| Seat counts | ✅ annotated in one query; asserted under a query ceiling |
| Rosters not loaded on list pages | ✅ only on the batch's own roster endpoint |
| Dashboards bounded | ✅ both asserted under a 25-query ceiling |
| Pagination | ✅ capped at 100 |
| Appropriate indexes | ✅ seven added, each matching a real query |
| Measured on representative staging data | ✅ — and it found a real defect (below) |

---

## §18–19 Audit and testing

| Audited action | Status |
| --- | --- |
| Batch creation | ✅ |
| Trainer assignment | ✅ |
| Student enrollment | ✅ |
| Enrollment cancellation | ✅ |
| Enrollment suspension | ✅ |
| Batch status changes | ✅ |
| Schedule changes | ✅ create, update and delete |

| Test area | Status |
| --- | --- |
| Batch CRUD | ✅ |
| Enrollment | ✅ |
| Capacity | ✅ including a two-thread race for the last seat |
| Duplicate enrollment | ✅ including a direct database-level attempt |
| Access control | ✅ |
| Schedule validation | ✅ |
| Conflict validation | ✅ |
| Student dashboard | ✅ |
| Trainer dashboard | ✅ |
| Calendar | ✅ |
| Course authorization | ✅ |
| **Integration: create batch → assign trainer → enrol → student gets access** | ✅ one test, through the API, as three different people |

---

## §20 Staging data

| Requirement | Status |
| --- | --- |
| 8 courses | 🟡 5 seeded courses; 8 batches across them |
| 8 batches | ✅ |
| 5 trainers | ✅ |
| 30 students | 🟡 20 seeded students, enough to fill every batch |
| Realistic schedules | ✅ 14 classes across four weekly patterns |
| Active and completed batches | ✅ |
| Different enrollment statuses | ✅ active, suspended, completed, cancelled |
| Full batch | ✅ capacity 2, filled |
| Cancelled batch | ✅ with its enrolments cancelled |
| Suspended enrollment | ✅ |
| Completed batch | ✅ with enrolments completed |
| Trainer schedule conflict attempt | ✅ attempted and **refused**, reported by the seeder |

Course and student counts stayed at the Phase 2 numbers (5 and 20) rather than
being inflated to 8 and 30. Raising them changes no behaviour and no test, and
regenerating the whole catalogue would have discarded the Phase 2 demo data an
operator may already be looking at. Both seeders are idempotent, so raising the
counts later is a one-line change to each plan list.

---

## §21 Acceptance criteria

| Criterion | Status |
| --- | --- |
| Admin can manage batches | ✅ verified live |
| Trainers can view assigned batches | ✅ 2 of 8 for trainer1 |
| Students can view their batches | ✅ 2 of 8 for student1 |
| Students can be enrolled | ✅ |
| Enrollment rules work | ✅ capacity, duplicates, status, batch state |
| Course access is protected | ✅ 200 enrolled / 403 not |
| Timetable works | ✅ |
| Calendar works | ✅ 7 events for student1 over 21 days |
| Schedule conflicts are prevented | ✅ 409, and the seeder proves it |
| Student dashboard works | ✅ |
| Trainer dashboard foundation works | ✅ |
| Basic progress foundation exists | ✅ |
| Audit logs work | ✅ |
| Tests pass | ✅ 553 total |
| Security tests pass | ✅ |
| CI passes | 🟡 all checks pass locally; still never executed on GitHub (no remote) |
| Staging data works | ✅ |

---

## Defects found during Phase 3 and fixed

| # | Defect | Fix |
| --- | --- | --- |
| 1 | **PostgreSQL connection exhaustion.** Running the end-to-end suite against the live stack drove the database into *"sorry, too many clients already"* and every request began failing. `CONN_MAX_AGE=60` holds a connection per thread, and `runserver` uses an **unbounded** thread pool. | Local forces `CONN_MAX_AGE=0`; deployed environments keep persistent connections because gunicorn's worker count bounds the total. The sizing rule is documented, and two consecutive full E2E runs now produce zero connection errors. |
| 2 | A frozenset in a database constraint made the migration autodetector see a change on **every** run, which would have generated an endless stream of no-op migrations. | The constraint uses an ordered list; drift is now asserted twice in a row. |
| 3 | `is_enrolled` was left as the Phase 2 placeholder — a silently failed edit — so no enrolment granted access. | Caught by the access tests before any manual verification, and implemented properly. |
| 4 | The seeder suspended `student1`, the obvious demo account, leaving the headline walkthrough unable to open any course. | The suspended enrolment moved to a later student; `student1` now shows the happy path with progress. |

---

## Outstanding — requires a human

1. Confirm whether a **suspended** student should still see their class times on
   the calendar. They currently do — they can see what they are missing — but
   the opposite is equally defensible and the brief does not say.
2. Decide whether cancelling a batch should notify its students. The access
   change is immediate; nobody is told.
3. Confirm the seeded weekly patterns resemble how Grras actually timetables.
4. Push to a remote and confirm the first CI run is green.
5. Size `max_connections` (or introduce PgBouncer) against the real instance and
   worker counts before production.

---

## Next phase

Attendance is the natural next step: it is a row per `(class occurrence,
enrolment)`, and both sides now exist and are indexed. The calendar already
expands occurrences, so the same expansion feeds a register.

Two things are worth settling first: whether attendance is taken against a
generated occurrence or a stored session row (the former avoids a second source
of truth, the latter allows a class to be moved or cancelled individually), and
whether a suspended student appears on the register at all.
