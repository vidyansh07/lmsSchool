# Architecture decisions

One entry per decision that a future reader might otherwise reverse by accident.
Newest last. Format: what was decided, what it rules out, and why.

---

### D-001 · Custom user model before the first migration
**Phase 0.** `accounts.User` with email login and a UUID primary key.
Swapping `AUTH_USER_MODEL` after tables exist is one of the hardest migrations
in Django, and every LMS table carries a foreign key to it. Sequential integer
keys would leak enrolment volumes and invite enumeration.

### D-002 · Session authentication, not JWT
**Phase 0/1.** `HttpOnly` session cookies with CSRF.
Buys XSS containment (script cannot read the credential) and immediate
revocation (deactivating a user ends access on the next request). Costs
statelessness, which this system does not need. Requires the frontend and API to
share a registrable domain in deployed environments.

### D-003 · Environment asserted at boot
**Phase 0.** Each settings module calls `require_environment()`; a mismatch with
`DJANGO_ENV` refuses to start. Makes "development config pointed at production"
impossible rather than merely discouraged.

### D-004 · Secure defaults in `base.py`, relaxations only in `local.py`
**Phase 0.** A forgotten override then fails towards *too strict*, which is
visible immediately, rather than towards insecure, which is not.

### D-005 · One error envelope, generic 500s
**Phase 0.** `{"error": {code, message, details, request_id}}` everywhere.
Unhandled exceptions log a traceback server-side and return a request id.

### D-006 · Failure audits are written outside the request transaction
**Phase 1.** `ATOMIC_REQUESTS` plus DRF's rollback on handled exceptions was
discarding the audit row for the very failure it recorded. Non-success entries
are queued and flushed by middleware.

### D-007 · Capabilities, not scattered role checks
**Phase 1.** `ROLE_CAPABILITIES` maps role → capability set; views declare the
capability they need. A new role is one table entry, not an audit of every view.
A role absent from the table gets base self-service rights only — fail closed.

### D-008 · Serializers scoped by caller
**Phase 1.** Separate read and write serializers per audience, all rejecting
unknown fields. One serializer with conditional field-stripping is where
privilege-escalation bugs live.

### D-009 · Uploads are re-encoded (images) or extension-paired (documents)
**Phase 1/2.** Images are re-encoded server-side, dropping EXIF. Documents
cannot be re-encoded, so the extension must agree with the magic bytes — a
signature check alone is useless when `.docx`, `.pptx` and `.zip` are all ZIP
containers. Stored filenames are always generated.

### D-010 · Gender is not collected
**Phase 1.** Nothing makes a decision from it. Data not collected cannot leak.
Adding it later is one migration.

### D-011 · Fee tracking is a status flag, not a ledger
**Phase 1.** `pending / partial / paid / waived / overdue`, administrator-set and
audited. No amounts, transactions, receipts or gateway. Half an accounting
system would create a second source of truth about money.

### D-012 · `courses` is one app, not three
**Phase 2.** Category, Course, Module, Lesson, Resource and VideoAsset are one
aggregate. The boundary that matters is not structural but a question — "who may
see or change this?" — and it lives in `apps/courses/access.py`.

### D-013 · Explicit ordering with a deferred unique constraint
**Phase 2.** `(parent, position)` unique, **deferred**. Creation date is not an
order. Deferral is what makes reordering possible: a reshuffle necessarily passes
through states where two rows share a position.

### D-014 · Video is metadata; the app stores no video bytes
**Phase 2.** Provider abstraction (external URL, S3, managed). The playable URL
is issued by a playback endpoint after an access check, never included in list
or detail payloads.

### D-015 · Trainers hold no global course or batch capability
**Phase 2/3.** Authoring rights come from `CourseAssignment`; batch visibility
from `Batch.trainer`. Removing the row removes the access on the next request.

### D-016 · Batches and enrolments are separate apps
**Phase 3.** Batch is *delivery* (exists with no students; institution-owned).
Enrolment is *participation* (one student's relationship, grows progress then
attendance, results, certificates). Dependency runs one way.

### D-017 · Capacity is locked; duplicates are a partial unique index
**Phase 3.** Capacity is a count of *other* rows, so the batch is locked with
`SELECT … FOR UPDATE`. Duplicate prevention *is* expressible in the database —
a partial unique index over live statuses only, so re-enrolling after a
cancellation stays legal.

### D-018 · Schedules store wall-clock time plus an IANA zone
**Phase 3.** A 09:00 class must still be 09:00 after a daylight-saving change.
Storing a UTC instant would silently move it twice a year. Overlap is compared
half-open (back-to-back classes are legal) and zone-aware.

### D-019 · Educational history is never deleted
**Phase 3.** Cancelling and suspending change a status and record why; progress
rows are untouched. A returning student finds their history intact, and a
certificate issued years earlier stays explicable.

### D-020 · One calendar, composed from registered sources
**Phase 3.** `EVENT_SOURCES` is a list of `(user, start, end) -> events`
functions. Each does its own access control; recurrence is expanded, not stored;
a failing source is logged and skipped rather than blanking the timetable.

### D-021 · Persistent DB connections only where concurrency is bounded
**Phase 3.** `runserver` uses an unbounded thread pool and `CONN_MAX_AGE` holds
a connection per thread — which exhausted PostgreSQL under the E2E suite. Local
forces `CONN_MAX_AGE=0`; deployed keeps persistence because gunicorn's worker
count bounds the peak at `instances × workers × threads`.

---

## Phase 4 onwards

### D-022 · SUPERADMIN and MANAGER added to the existing matrix
**Phase 4.** The contract requires five roles. Added as two rows in
`ROLE_CAPABILITIES` rather than a new permission system — which is exactly what
D-007 was built for. `SUPERADMIN` holds every capability including platform
administration; `MANAGER` holds academic operations but not user-role changes or
platform settings.

### D-023 · Class sessions are stored rows, generated from schedules
**Phase 4.** Attendance must attach to a *specific* class, which has to survive
the schedule changing afterwards. A purely derived occurrence cannot be
cancelled, rescheduled or given a topic. Sessions are therefore materialised
from `BatchSchedule` by an explicit generation step, keeping the schedule as the
rule and the session as the event.

### D-024 · Academic rules are configuration, not code
**Phase 4.** Attendance requirement, marks rules, late-submission policy and
completion requirements live in a settings model with per-course overrides.
§4.7 forbids hard-coding business rules into views; a rule change must not
require a deployment.
