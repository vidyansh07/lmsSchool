# Batches, enrolment and scheduling

How Phase 3 connects people to courses, and why it is built this way.

---

## 1. The shape

```
Course ──┐
         ▼
      Batch ──── BatchSchedule (weekly slots)
         │  └─── trainer: TrainerProfile
         ▼
    Enrollment ──── student: StudentProfile
         │
         └──── LessonProgress (per lesson)
```

Two apps, not one:

* **`apps.batches`** is the *delivery* side. A batch exists whether or not
  anyone signs up; it is owned by the institution.
* **`apps.enrollments`** is the *participation* side. It is a student's
  relationship with a batch, and it grows its own concerns — progress now,
  attendance and certificates later.

The dependency runs one way, `enrollments → batches → courses`, so adding a
progress field never touches the timetable.

---

## 2. What a constraint cannot express

Three rules in this phase are relationships between rows, not properties of one,
so none can be a column check. Each is handled where it can actually be correct.

| Rule | Where | Why not a constraint |
| --- | --- | --- |
| **Capacity** | `enrollments.services`, under `SELECT … FOR UPDATE` | It is a count of *other* rows. Two requests arriving together would both read "one seat left". |
| **One live enrolment per student per batch** | A **partial unique index** | This one *is* a database constraint — unique across live statuses only, so a student may re-enrol after cancelling. |
| **Schedule conflicts** | `batches.conflicts`, before every write | Overlap spans three dimensions across two rows. |

Capacity has a test that races two threads for the last seat; the duplicate rule
has a test that bypasses the service entirely and asserts the database refuses
the insert.

---

## 3. Overlap, precisely

Two weekly slots clash only when **all three** hold:

1. **Same weekday.** Monday 09:00 and Tuesday 09:00 never clash.
2. **Overlapping times**, compared half-open: `start_a < end_b and start_b < end_a`.
   A class ending at 11:00 and one starting at 11:00 do **not** clash —
   back-to-back classes are normal and must stay allowed.
3. **Overlapping batch date ranges.** Two Monday-morning slots in batches that
   run in different months never meet.

Times are compared in each slot's own zone, so 09:00 in Kolkata and 09:00 in
London are correctly treated as different moments.

Candidates are narrowed in the database first — same weekday, active, batch not
cancelled, date ranges overlapping — so the Python comparison runs over a handful
of rows rather than the whole timetable.

### Why wall-clock times, not UTC instants

A class that meets at 09:00 local should still meet at 09:00 after a
daylight-saving change. Converting to UTC at write time would silently move it
by an hour twice a year, so the slot stores a wall-clock time plus an IANA zone
name and resolves to an instant only when it is displayed or compared.

---

## 4. Course access

This is the rule Phase 2 left a seam for. A student reaches non-preview content
only when **all** of these hold:

1. Their account is active.
2. They hold an enrolment whose status is `active` or `completed`.
3. That enrolment's batch is not cancelled.
4. Today is inside the access window, where one is set.

`Enrollment.grants_access()` owns all four, and `courses.access.is_enrolled`
calls it. One definition, consulted live on every request — so suspending an
enrolment closes the door on the very next call, with no cache to invalidate.

**`COMPLETED` grants access on purpose.** A student who finished the course keeps
the material they studied. `SUSPENDED` does not — that is what suspending means.
`PENDING` does not either: the place has not been confirmed.

---

## 5. History is never destroyed

Cancelling and suspending change a status and record why. They do not delete the
enrolment, and they never touch `LessonProgress`.

That matters for three reasons: a returning student finds their history intact,
a dispute months later can still be answered, and a certificate issued from a
completed enrolment must still be explicable years afterwards. The audit entry
for a cancellation carries `history_preserved: true` so that intent is legible
to somebody reading the log rather than the code.

Cancelling a *batch* cascades to its enrolments, because access derives from the
batch and leaving enrolments "active" underneath a cancelled one would be a
contradiction waiting to be misread.

---

## 6. One calendar

§10 asks for a single calendar abstraction rather than one per feature, and
`apps/dashboards/calendar.py` is it. Every source is a function
`(user, start, end) -> list[CalendarEvent]`, and the registry composes them:

```python
EVENT_SOURCES = [class_events, batch_milestone_events]
```

Adding assignment deadlines, quiz windows, exam dates or announcements later
means writing one function and appending it. No view, no serializer and no
frontend component changes.

Three properties are deliberate:

* **Each source does its own access control.** There is no "the calendar sees
  everything" shortcut; a source resolves visibility through the same access
  layer the rest of the API uses.
* **Recurrence is expanded, not stored.** A weekly slot is a rule. Materialising
  a row per week would mean rewriting history every time a schedule changed.
* **A failing source is logged and skipped.** One broken feed must not blank out
  somebody's whole timetable.

The window is capped at 120 days: a calendar query is cheap per day and
expensive per year.

---

## 7. Progress, deliberately minimal

§13 asks for the *architecture*, not the system. What exists is a row per
`(enrolment, lesson)` carrying a status, when it was first and last opened, and
when it was finished — plus a derived course percentage counting published
lessons only, so a draft lesson an author is still writing cannot make a
student's progress bar go backwards.

Keyed on the **enrolment**, not the user: the same person may take the same
course twice in different batches, and those are different attempts with
different progress.

Watch position, time on task, completion rules and gated progression all attach
to this row without reshaping it.

---

## 8. Query cost

§17 asks for efficient queries measured on representative data. What is in place:

| Concern | Approach |
| --- | --- |
| Seat counts on a batch list | `with_counts()` annotates in one query; a page of 20 batches costs one, not 21 |
| Batch and enrolment lists | `select_related` on course, trainer, student and their users |
| Dashboards | Enrolments fetched once with their relations; both dashboards are asserted under a query ceiling in tests |
| Rosters | Never loaded on a list page — only on a batch's own roster endpoint |
| Listings | Paginated, capped at 100 per page |
| Indexes | `(student, course, status)` for the access check, `(batch, status)` and `(course, status)` for rosters and reporting, `(course, status)` / `(trainer, status)` on batches, `(batch, weekday)` and `(trainer, weekday)` on schedules |

### The connection-exhaustion trap

Found by running the end-to-end suite against the live stack: with
`CONN_MAX_AGE=60`, the Django dev server exhausted PostgreSQL's
`max_connections` and every request began failing with *"sorry, too many clients
already"*.

The cause is that `runserver` handles each request on a thread from an
**unbounded** pool, and a persistent connection is held per thread. So:

* **Local** forces `CONN_MAX_AGE=0`. Reconnecting per request costs a millisecond
  and the concurrency has no ceiling.
* **Deployed** keeps persistent connections, because gunicorn's worker and thread
  counts are fixed. The peak is `instances × workers × threads`, which must stay
  under `max_connections` with headroom for migrations and `psql`. Beyond a
  handful of instances, put PgBouncer in front rather than raising
  `max_connections` — each PostgreSQL connection costs real memory.

---

## 9. Who may do what

| | Administrator | Trainer | Student |
| --- | :---: | :---: | :---: |
| See every batch | ✅ | — | — |
| See own batches | ✅ | ✅ (assigned) | ✅ (enrolled) |
| Create / edit a batch | ✅ | — | — |
| Assign a trainer | ✅ | — | — |
| Manage a timetable | ✅ | — | — |
| See a batch roster | ✅ | ✅ (own batches) | — |
| Enrol a student | ✅ | — | — |
| Change an enrolment's status | ✅ | — | — |
| See own enrolments | ✅ | ✅ (own batches') | ✅ (own only) |

A trainer viewing their batch is not the same as managing it. Capacity, dates
and status are institutional decisions, so a trainer is refused — and cannot
assign themselves to a batch either.

Students cannot see a batch roster. A classmate list is other people's personal
data, and nothing in this phase needs it.
