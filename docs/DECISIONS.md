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

### D-025 · An assignment belongs to a course, and may be narrowed to a batch
**Phase 4.3.** The work is about the *subject*, so `course` is required and
`batch` is optional. A null batch means every cohort running that course, which
is the common case and stops a trainer re-creating the same exercise each
intake. A batch-specific assignment is matched per enrolment, so a student on
the morning batch never sees work set for the evening one.

### D-026 · A resubmission is a new attempt row, never an overwrite
**Phase 4.3.** Keyed `(assignment, enrollment, attempt)`. The first attempt, its
marks and the feedback that prompted the rework all survive, so a dispute months
later can be answered and progress reporting can see the history rather than
only the last state. Returning work for rework always opens one more attempt,
independently of the resubmission limit — that is what "returned" means.

### D-027 · Submitted files are stored inert and served as opaque attachments
**Phase 4.4.** Student uploads include source code, which cannot be re-encoded
the way an image is. Instead the *storage* is neutralised: every submission is
written as `<uuid>.bin` under a server-generated path, and every download is
`application/octet-stream`, `attachment`, `nosniff`, with a sandbox CSP. An
`.html` or `.php` hand-in is therefore never rendered or executed by anything —
there is no interpretable file on disk and no renderable response. Archives are
stored and never unpacked; code is never read, parsed or run.

### D-028 · `course.coursework`, not `course.assignments`
**Phase 4.3.** `course.assignments` was already taken in Phase 2 by
`courses.CourseAssignment`, which assigns *authors* to a course. Renaming that
would have touched working code and a shipped migration for a cosmetic gain, so
the academic work reverses as `course.coursework`.

### D-029 · A weekly test is an assessment with a delivery mechanism
**Phase 4.5.** §4.5 requires that the LMS not depend on Google Forms. So
`Assessment` holds the schedule, the marks and the rules, and `delivery` says
how it is taken: an external link, a file upload, or offline. A native quiz
engine is one more delivery value plus one more result source — Phase 5's job,
deliberately not listed as a choice that does nothing today.

### D-030 · A file-upload assessment is backed by an assignment
**Phase 4.5.** Rather than build a second upload pipeline, a file-delivered
test creates an `Assignment` alongside itself. That reuses the §4.4 file rules,
the attempt logic and the grading path instead of reimplementing them, and
grading the backing assignment writes the result through the same
`record_result` every other path ends in.

### D-031 · Result import is preview, then confirm
**Phase 4.6.** The first request reads the file, validates every row against
the live database and stores a report; it writes nothing. Only an explicit
confirmation applies it, in one transaction, re-resolving every student — so a
class list that changed in between fails the import rather than half-applying
it. Formula cells are refused rather than stored, because a stored `=…` becomes
a spreadsheet-injection payload the next time the data is exported.

### D-032 · Academic rules live in a table, in two layers
**Phase 4.7.** One institution-wide row and optional per-course overrides;
`NULL` means inherit. Resolution walks course → institution → code default, so
there is always an answer and never a crash on a missing row. Deliberately not
per-batch: an intake that grades differently from the one before it is an
administrative accident, and every extra layer is another place a rule can
hide. The resolved policy is memoised per request rather than cached, so a rule
change takes effect on the very next request instead of when a TTL expires.

### D-033 · Nobody may grant a role they do not hold
**Phase 4.** Adding SUPERADMIN opened a privilege escalation: an administrator
holds `user.change_role`, so without a rule they could set a role granting
`platform.configure` — which the ladder withholds from them — and then use the
promoted account. `can_grant_role` requires containment: a role may be granted
only when everything it can do is something the actor can already do. Enforced
in the service, so the admin site and any future command obey it too.

---

## Phase 5

### D-034 · A project's workflow lives on the student's row, not the brief
**Phase 5.1.** `Project` is the brief and has a publishing lifecycle;
`StudentProject` is one person's work and carries the eight-state review loop
(assigned → in progress → submitted → under review → rework → approved →
completed). Rework returning to in-progress is exactly what distinguishes a
project from an assignment, and it needs somewhere per-student to live. The row
is created on demand, so a student who enrols after the project was handed out
still gets one without anybody remembering to re-assign.

### D-035 · A rubric must add up to the marks the project is out of
**Phase 5.1.** Validated on save. Otherwise a perfect score on every criterion
would not equal full marks, and nobody would notice until a student disputed a
grade. The reviewer sends per-criterion scores and the **server** sums them —
§5.5's rule about browser-submitted totals, applied to projects.

### D-036 · Project files reuse the assignment upload pipeline exactly
**Phase 5.3.** §5.3 asks for "the same secure upload controls as assignments".
The only way that stays true is one implementation: `ProjectFile` uses
`submission_upload_to` and `validate_submission_upload`, and the download view
sets the same octet-stream, attachment, nosniff and sandbox-CSP headers.
Archives are stored and never unpacked; no student code is read, parsed or
executed anywhere in this codebase.

### D-037 · An exam attempt owns its own paper
**Phase 5.5.** When a candidate starts, the questions drawn are frozen into
`AttemptQuestion` rows with the marks they were worth and the order the options
will be shown in. Everything afterwards — refresh, closed browser, marking, a
dispute months later — reads that copy. Editing the bank therefore cannot
rewrite a paper already sat, and a question that has been sat is refused an edit
so the bank cannot disagree with what was marked.

### D-038 · Expiry is applied lazily, not swept
**Phase 5.5.** `expires_at` is written once from the server's clock and never
recomputed. There is no background worker in this deployment, so an attempt is
finalised the next time anybody touches it, grading whatever was auto-saved
before the deadline. That is the same outcome a sweep would produce, without
depending on a component that does not exist. When a worker arrives, it calls
the same `finalise_expired`.

### D-039 · Starting an exam is idempotent, including under a race
**Phase 5.6.** Two starts can arrive at once — a double-clicked button, a
re-rendered component, two tabs. The unique index on
`(exam, enrollment, attempt_number)` stops the second row; the service catches
that inside a savepoint, reads the attempt that won, and returns it. Refusing
the second caller would be refusing somebody who asked for exactly what already
exists. Covered by a threaded test, which is the only way to reach it.

### D-040 · Papers are drawn with a system RNG, not `random`
**Phase 5.5.** Which questions a candidate draws, and the order their options
appear in, are the difference between two papers. A predictable stream would let
anyone who could observe one paper narrow down another's — a cheating vector in
an examination, even though it is harmless in an ordinary shuffle.

### D-041 · A candidate's serializer has no answer fields at all
**Phase 5.4/5.5.** `is_correct`, `answer_key` and `explanation` are absent from
the class the candidate is served, rather than blanked or filtered downstream. A
field that is not on the serializer cannot be leaked by a later change to a
view. For the same reason the question bank returns an empty queryset to
students: it holds the answers, so there is no student-facing read of it.

---

## Phase 6

### D-042 · One progress calculation, and it lives in the backend
**Phase 6.3.** `apps.progress.reports.progress_report` is the only place that
answers "how far is this student?". Every screen and every completion rule reads
it; nothing divides two counts of its own. A dashboard that computes its own
percentage is how two parts of a product come to disagree about whether somebody
has finished — and the one that is wrong is always the one nobody tested.

### D-043 · Rules produce numbers plus a verdict, and report themselves when off
**Phase 6.4.** Each of the seven conditions §6.4 names is a rule reading the
report and the resolved policy. A rule that is switched off still comes back,
with `required: False` and its numbers intact, so a screen can say "attendance
78% (not required on this course)" rather than pretending attendance does not
exist. A rule with nothing to measure — a course that sets no projects — passes;
the alternative blocks every student on that course and takes months to notice.

### D-044 · Eligibility is derived; approval is decided
**Phase 6.6.** Eligibility is recomputed on every read, so lowering a threshold
moves it immediately. Approval is stored with who decided it, when, and a
`rule_snapshot` of what the rules said at that moment — never recomputed. That
is what lets the system answer "why does this student have a certificate on 62%
attendance?" a year later. An approval is not undone by a later rule change: a
student who dips below the line after graduating has not un-graduated.

### D-045 · Online and offline are a field, not a second product
**Phase 6.5.** `Batch.delivery_mode` with an optional per-student override on
the enrolment. Online and offline students share the same courses, batches,
sessions, attendance, assignments, projects, exams and certificates. What
differs is which completion rules an institution turns on — configuration, not
architecture. An offline cohort switches the lesson requirement off and
everything else is unchanged.

### D-046 · A certificate is a snapshot, and its code is not its number
**Phase 6.7/6.8.** The student's name and course title are copied onto the row at
issue, so renaming a course in 2027 cannot change what a 2026 certificate says;
correcting a name is a *reissue*, with the old one superseded and both kept. The
public endpoint takes `verification_code` — 160 bits from `secrets` — not the
sequential number, so anyone holding one certificate cannot enumerate the rest.

### D-047 · Revocation is a state, not a delete
**Phase 6.7.** A revoked certificate still verifies, and says it was revoked.
Deleting it would make a forgery unfalsifiable: the checker would see "not
found" for both a fake and a withdrawal, which is exactly the wrong answer.

### D-048 · The public verification response is an allowlist, built in the service
**Phase 6.8.** `public_view` writes out the nine fields by hand rather than
excluding fields from a model serializer. The risk on a public endpoint is
*addition*: a field added to the model later would otherwise appear on the
internet the same day. Deliberately absent: email, phone, marks, attendance, the
enrolment, the student's internal id, and the batch code.

---

## Phase 7

### D-049 · The in-app notification is the notification; email is a channel
**Phase 7.1.** A `Notification` row is written first and always. Delivery runs
afterwards through a channel registry, so a mail outage costs a student an email
and not the information. Adding SMS or push later is one class and one line in
`CHANNELS` — that is what "provider-agnostic" has to mean to be worth saying.

### D-050 · A notification never breaks the thing it describes
**Phase 7.1.** `notify` swallows every exception, not only database errors: it
is called from inside grading, issuing and publishing, and none of those should
become a 500 because a courtesy message failed. Delivery is deferred to
`transaction.on_commit`, so a notification for work that was rolled back is
never sent.

### D-051 · Email templates are code, not rows
**Phase 7.2.** A database-editable template is text that leaves the building
under the institution's name, and making it worth editing means accepting
markup. What an operator actually wants to change — the institution name, the
signature — is configuration. Named renderers returning plain text keep the
injection surface at zero.

### D-052 · The outbox is a table, so retry needs no broker
**Phase 7.2.** A row exists before the provider is called, carrying status,
attempts and a scrubbed error. `send_pending_email` drains it with exponential
backoff and gives up after four attempts. When a worker arrives it calls the
same function and the command becomes the manual fallback rather than the
mechanism.

### D-053 · Secrets are scrubbed inside free text, not only by key
**Phase 7.2.** A provider's exception message is a sentence, and the credential
it names arrived as prose (`auth failed for password=…`), not as a dictionary
key. `scrub_text` redacts `key=value` pairs and bearer tokens wherever they
appear, and every string value now passes through it. Found by a test that
asserted the stored error carried no password.

### D-054 · An announcement's audience is a rule, not a stored list
**Phase 7.3.** Addressed to everyone, a course, a batch or named people, and
resolved when it is read. A student who joins tomorrow sees the notice on the
board; they do not retroactively receive yesterday's notification. The
noticeboard and the notification are different things and it is right that they
disagree.

### D-055 · Discussions are per batch, and moderation hides rather than deletes
**Phase 7.6.** A thread belongs to a batch — no following, no profiles, no
feed, no cross-batch anything, because §7.6 says not to build a social network.
A hidden reply keeps its row, its author still sees it, and the reason is
recorded: a deleted message leaves a conversation that makes no sense and
nothing to appeal to.

### D-056 · The class list is names only, and it is configuration
**Phase 7.7.** Full name and student id, never an email or a phone number, and
the whole thing is behind `batch_directory_visible` so an institution that does
not share class lists can switch it off. There is no mechanism for a student to
opt in to being contactable, and no reason to invent one for this product.

### D-057 · Gamification deliberately not built
**Phase 7.8.** Bookmarks and lesson notes are built, because they are working
tools a student asks for. Badges, points and streaks are not: §7.8 makes them
conditional on not destabilising core learning, and a scoring system that has to
be recomputed whenever a completion rule changes is exactly the kind of coupling
that destabilises it. The hook is `apps.progress` if it is ever wanted.

---

## Phase 8

### D-058 · Every metric carries its own definition
**Phase 8.6.** §8.6 requires documented definitions, so a metric *is* a
`Metric` dataclass holding its definition, and the API returns the definition
next to the number. The definitions are specific about the awkward cases — what
counts as enrolled, whether an absence is a sitting, which of several attempts
is measured — because those are exactly the choices that make two
implementations of "completion rate" disagree by ten points and nobody notice
for a quarter.

### D-059 · A rate over nothing is null, never zero
**Phase 8.6.** "0% of nothing completed" reads as a failure when it means there
was nothing to complete. Every rate returns `None` when its denominator is zero,
and the interface renders that as an em dash.

### D-060 · A report is a scoped queryset plus a producer
**Phase 8.3.** The caller's visible batches and enrolments are resolved first,
and the report runs on those. There is no fetch-everything-then-filter path, so
a trainer asking for a batch they do not teach gets an empty report rather than
somebody else's numbers — and a filter cannot become a way to widen access.

### D-061 · An export is the same report, streamed
**Phase 8.5.** One producer, two renderings: JSON for a screen (bounded to a
page) and a `StreamingHttpResponse` for a download. What is exported and what is
on screen cannot disagree, and nothing holds a whole institution in memory.
Exporting needs its own capability: reading a page and walking out with the
whole dataset are different acts.

### D-062 · Exports neutralise spreadsheet formulas
**Phase 8.5.** A cell beginning `=`, `+`, `-` or `@` is executed by Excel when
the file is opened, on the machine of whoever opened it. Every exported value is
prefixed with an apostrophe. This is the mirror of the import-side refusal in
§4.6: formulas are refused coming in and neutralised going out.

### D-063 · A bulk import never silently modifies an existing person
**Phase 8.5.** A student row whose email already exists is *reported*, not
applied. Matching an existing account is fine; a spreadsheet quietly renaming
somebody or changing their role is not, and the operator who uploaded the file
would never know. Confirmation re-checks every row against the database and
rolls the whole import back if anything changed in between.

### D-064 · Holidays are configuration that class generation obeys
**Phase 8.1.** The academic calendar is not decoration: generation skips
holidays and reports how many days it skipped. A term break that silently
produced thirty classes nobody attended would leave thirty empty registers to
explain afterwards.

### D-065 · The readiness cache probe uses a unique key per probe
**Phase 8, found in an end-to-end run.** A shared probe key meant two overlapping
readiness checks deleted each other's value and reported a healthy cache as
broken. In production that reads as an unhealthy instance and pulls a live node
out of rotation — the exact failure a readiness probe exists to prevent. Covered
by a threaded test.

---

## Phase 9

### D-066 · Student files are private in three ways, not one
**§14.3.** No ACL stamped on upload, signed URLs that expire, and a boot check
that refuses a public bucket. Any one of the three alone is a control that
somebody can misconfigure without noticing — the bucket is world-readable, the
uploads are fine, and nobody finds out until a search engine does.

### D-067 · Downloads still go through the application
**§14.3.** Handing the browser a signed URL is faster and cheaper, and it puts a
bearer token in an address bar: browser history, referrers, and whatever the
student pastes into a chat. Streaming through the view keeps one authorization
check in one place. The seam for offloading exists if the cost ever justifies
the trade.

### D-068 · An unavailable malware scanner refuses the upload
**§14.3.** Failing open keeps the site working during a scanner outage, and
makes "take the scanner down" a complete bypass. An institution that cannot
accept assignments for an hour is having a bad day; one that accepted a
malicious file because a health check flapped has a different kind of problem.
The refusal message never names the detection: that would turn the endpoint into
an oracle for tuning a payload until it passes.

### D-069 · The outbox row is written in the request; only the send is queued
**§14.10.** Queue-first loses every message written while the broker is down —
including every password reset. Row-first means a broker outage makes mail late
rather than absent, because the scheduled sweep finds the PENDING row. The cost
is one insert in the request, which is not the slow part.

### D-070 · Credential email is never queued
**§14.10, §14.5.** The body of a reset email *is* the credential. The outbox
would keep it in a database table and the task payload would keep it in Redis,
both readable by anyone with operational access. So reset and verification mail
is sent inline, on endpoints already limited to a handful of requests a minute.
A slow request on a rare endpoint beats a reset link with a shelf life.

### D-071 · Exports and imports stay synchronous
**§14.10.** Measured rather than assumed. Exports already stream through a
generator into a `StreamingHttpResponse`, so the whole institution costs one row
of memory. Imports are capped at 2,000 rows and 2 MB and must be all-or-nothing
in one transaction; backgrounding would turn "these 14 rows are wrong, here they
are" into a job the operator has to come back for. Revisit if either cap rises
or a p95 crosses a few seconds.

### D-072 · The cohort report shares one gathering, not one calculation
**§14.9.** `progress_report` cost seventeen queries per student, so a page of
five hundred was eight thousand round trips. The fix could not be a second,
bulk implementation of the arithmetic — that is how two screens come to disagree
about whether somebody has finished. Instead `ProgressInputs` gathers the
*inputs* for a set of enrolments and the same section functions read from it.
A test asserts the bulk path and the single path produce identical reports.

### D-073 · Grouped metrics live beside their definitions
**§14.9.** `metrics.by_batch` computes completion, attendance and pending
marking for many batches in four queries. It sits in `metrics.py`, not in the
report that needed it, and a test asserts it agrees with the scalar functions
for the same batch. A batch report showing 71% while the metrics page shows 68%
would be worse than either being wrong: nobody would know which to believe.

### D-074 · Three plain queries beat one clever one
**§14.9.** Annotating a student count and two attendance counts onto one
queryset made PostgreSQL count rows in the product of enrolments, sessions and
attendance records: eight queries, four seconds, and a query-count test would
have passed it. Split into three grouped counts it is eighteen milliseconds.

### D-075 · Every 403 is audited centrally
**§14.6.** Refusals were recorded only where a view wrote one by hand, so the
most common kind — a refusal by the permission class, which is what fires when
somebody probes an endpoint — left no trace. Someone reading the log to answer
"did anybody try?" would have seen nothing and concluded nobody did. CSRF
failures are excluded: a browser-integration fault, not an attempt to exceed
authority, and they would drown the signal.

### D-076 · Two database roles
**§14.8.** The application connects all day with credentials sitting in a
container's environment; migrations run rarely from a controlled place. Giving
the everyday connection DDL rights makes a leaked application password a leaked
ability to destroy the records. `grras_app` reads and writes rows and cannot
create, alter or drop anything — nor edit the audit log.

### D-077 · Redundant indexes removed
**§14.8.** Seven explicit `models.Index` declarations duplicated the index
Django already creates for a foreign key. A duplicate index serves no read and
taxes every write. A schema test now fails if another appears.

### D-078 · The scale dataset lives in its own database
**§14.9.** `seed_scale_data` builds hundreds of students and thousands of
records, which is what performance work needs and what the demo cannot have:
twenty-four generated courses push the demo ones off the first page of the
paginated catalogue, and the end-to-end suite — which finds them by name — fails.
Discovered the direct way. The command flushes cleanly and the constraint is in
its docstring.

### D-079 · Every paginated list carries a unique tiebreaker
**§14.4, §14.9.** SQL does not promise an order for rows that tie on the ORDER
BY columns, and pagination runs the query more than once — so a list ordered by
a nullable timestamp can show a row on two pages and never show another. Most
orderings here are on exactly such a column, and every row a feature creates in
one action shares a timestamp, so ties are the normal case. `DefaultPagination`
appends the primary key to any ordering that does not already end there, so a
list added later cannot forget.

Found by an end-to-end journey that could not see the project it had just
created: it was on page two, behind thirty-seven that all sorted equally.

### D-080 · A student's work list is ordered by due date, then by newest
**§14.9.** `("due_at",)` alone put newly-set work in an arbitrary position among
every undated task on the course. The secondary key is what makes "here is what
you have just been given" true.

### D-081 · Archiving a brief is a control, not a database operation
**Found in Phase 9.** Assignments and projects both had an `archived` status the
API accepted and no screen offered, so the only way to retire a finished brief
was a shell. Now the teaching pages expose Archive alongside Publish and Close,
and say plainly what it does and does not do: students stop seeing the brief,
and the work already handed in is untouched. The same gap as Phase 8's missing
Reopen, found the same way — an end-to-end journey with nowhere to put its
leftovers.

---

## Phase 10

### D-082 · Staging speaks https, rather than staging having weaker cookies
**§15.4.** `config.settings.hardened` marks the session cookie `Secure`
unconditionally, so a browser on plain http silently refuses to store it: sign-in
appears to succeed and the next request is anonymous. The two options were a
certificate or a weakened setting. Weakening it would mean staging no longer
tests what production runs — which is the only reason staging exists — so Caddy
terminates TLS with a certificate it issues itself, and Playwright is told the
certificate authority is not what is under test.

### D-083 · The Content-Security-Policy carries a nonce, and the app renders per request
**§15.2, found by running the production build.** `script-src 'self'` blocked
Next's inline bootstrap, so every page rendered and nothing hydrated — markup
with no behaviour, no error, nothing in a log. It had never been seen because
the end-to-end suite only ever ran the dev server, which takes an
`'unsafe-inline'` branch.

Three things had to be true together: a per-request nonce (middleware, not a
static header), `dynamic = 'force-dynamic'` (a prerendered page was built before
the request and carries no nonce), and *no* `'strict-dynamic'` (it makes the
browser ignore `'self'`, which refuses the bundle chunks). The cost of forcing
dynamic rendering is close to nothing here: every page is behind authentication
and fetches its data in the browser.

### D-084 · A stale CSRF token is retried once
**Found by the journey.** Django rotates the CSRF token when a session begins or
ends, so the cookie held from before a sign-out is no longer the one the server
expects — and because *a* cookie is present, nothing prompts a refresh. The
symptom is specific: sign out, sign back in, and the first action fails once,
then works. `apiMutate` now forces one refresh and one retry, only for
`csrf_failed`, so a genuine refusal is still a refusal.

### D-085 · Object storage in staging is MinIO, not a mock
**§15.4.** §15.4 asks for external S3 and no bucket exists for this project. A
mock would have tested the seam and not the protocol; MinIO speaks the same
protocol to the same boto3 client, so staging exercises private objects, signed
URLs and the real upload path. Moving to AWS is a change of
`AWS_S3_ENDPOINT_URL`. Running it also found that boto3 was signing with the
deprecated SigV2 against a custom endpoint — which every AWS region created
after 2014 rejects. The signature version is now pinned.

### D-086 · The mandatory journey creates a student and then learns as a seeded one
**§15.2.** An administrator never learns a new user's password: §1 has them send
a set-password link instead. That is a security property, and it means a browser
test cannot sign in as an account it just created. So the journey creates and
enrols a student for real — those are the steps under test — and runs the
learning half as a seeded student enrolled on the same batch by the same
administrator. The alternative was to weaken account creation for the
convenience of a test.

### D-087 · The journey waits out the rate limit rather than raising it
**§15.2.** It signs in about a dozen times from one address inside two minutes,
which is exactly the traffic the auth throttle exists to refuse. Raising the
limit for staging would make credential stuffing cheaper in the environment
built to behave like production. The test waits, the way a person would.

### D-088 · A backup is not verified until it has been restored
**§15.7.** `backup.sh --verify` restores into a scratch database, counts what
arrived, and prints every identifier sequence. The sequences are the reason:
a restore that brought every table and no sequences would hand the next student
an identifier somebody already holds, and nothing would complain until two
people had `GRS-S-00041`.

### D-089 · The secret scan proves what it skips is ignored
**§15.9.** `.gitleaks.toml` skips `.env` and `.env.staging` so a local
filesystem scan does not report files that cannot be committed. That skip is
only safe while they are genuinely git-ignored, so `make secrets` checks it —
verified by removing the `.gitignore` entry and watching the gate fail.

### D-090 · Two dead client functions became controls
**Found by the journey.** `generateSessions` and `setLessonCompletion` were
written, typed, and called from nowhere. So an administrator could set a
timetable and never turn it into classes, and a student could read a lesson and
never mark it done — while the completion rules counted completed lessons.
A capability that exists in the API and nowhere in the interface is not a
feature; it is a gap with a plausible-looking implementation in front of it.

### D-091 · The mandatory journey runs on its own, not inside the suite
**§15.2.** It signs in about a dozen times. Inside the suite the credential rate
limit is already exhausted by the tests before it, so it spends twelve minutes
waiting out throttles that exist only because of them — and it changes its
people's world, which the other specs then read. Alone it takes ninety seconds.
Gated behind `E2E_RELEASE_JOURNEY=1` because Playwright runs every configured
project by default, which would put it straight back in the suite it was
separated out of.

### D-092 · One sign-in helper, waiting for the session rather than the greeting
**Found by running the suite against the production build.** Nine copies of the
helper all waited for "Welcome back". The landing page renders on the server and
swaps to its signed-in form once the browser has fetched the current user, so
the greeting arrives a beat after the session does — twenty-four tests failed on
staging and none locally, which is the most expensive kind of difference between
environments. The shared helper waits for the Sign out control, which appears
exactly when there is a session, and waits out a 429 rather than asking for the
rate limit to be raised.

### D-093 · A cancelled batch is not teaching today
**Found by the journey.** Cancelled batches still put their classes on a
trainer's daily list, above the real one. Their students have lost access, so
the register would record attendance nobody can act on — and the ordering is how
a trainer comes to open the wrong class. Excluded at the "today" view rather
than from visibility, because an administrator must still be able to see the
history.

### D-094 · A seeder that dies part-way is worse than one that skips
**Found re-seeding.** `seed_academics` let `generate_sessions`' refusal escape,
so a single batch with no weekly pattern stopped the whole command at batch
three and left an environment neither empty nor complete — and a re-run failed
in the same place. It now skips those batches and says how many.

---

## Phase 11

### D-095 · Authority is a rule about the target, not only about the role granted
**§11.1.** `can_grant_role` answered "which role may I hand out?" and was
enforced everywhere. Nothing answered "whose account may I touch at all?", and
the two are not the same question. An administrator could not promote anybody
above themselves, and *could* edit a superadmin's email address — then send that
address a password-reset link — or simply deactivate them. Authority flowed
upward through a door nobody had thought to close.

`can_administer` closes it, in the service layer so the admin site, a management
command and any endpoint added later obey the same rule. The shape: a superadmin
may administer anyone; everybody else may administer only roles holding strictly
fewer capabilities than their own; nobody administers themselves through the
staff path.

### D-096 · A superadmin may administer another superadmin
**§11.1, §11.3.** The one lateral move on the ladder, and it is deliberate. If a
superadmin account is compromised, somebody has to be able to deactivate it. An
institution with one unremovable account is worse off than one whose top can
police itself. Every such act is audited with both roles.

### D-097 · An authority refusal is a 403, not a validation error
**§11.1.** The request was well formed and the caller is who they say they are;
they simply have no authority over that account. A 400 tells an interface to
highlight a field, and there is no field to fix. The message says only
"authority" — "you cannot edit a superadmin" tells an attacker which accounts
are worth pursuing.

### D-098 · The server says whether the caller may administer; the screen obeys
**§11.2.** Viewing is a wider permission than administering — an administrator
may legitimately see that a superadmin exists — so a screen that inferred edit
rights from "can I read this?" offered a form whose Save button was going to
fail. `AdminUserDetailSerializer` now returns `can_administer`, computed for the
requesting user, and the page renders a read-only record when it is false. It
informs the interface; the service answers the same question again on write.

### D-099 · Changing somebody's email is not a field edit
**§11.2.** It is the login identifier. So an administrator changing it marks the
address unverified, ends every session the account has open, and sends a
verification link to the new address — and it is audited as its own action with
both addresses, because "who changed this person's email and when" is the first
question asked after a takeover. Leaving the verified flag set would let an
administrator hand an account an address they control and have it trusted.

### D-100 · Administrators send links, never passwords
**§11.2.** There is no "set their password" control, deliberately. An
administrator who sets a password has to transmit it: two people then know it,
and the record says an administrator changed it rather than the owner setting
one. The screen sends a reset or verification link and says so.

Verification cannot be granted by hand either. An administrator may revoke it
(by changing the address) and may resend the link, but marking an address
verified is asserting a fact only the inbox owner can establish.

### D-101 · Light only, and measured
**§11.4.** The app followed `prefers-color-scheme`, so the same install looked
different on two machines and nobody could say what the product looked like. It
is now light everywhere.

Built as a light palette rather than an inverted dark one, which shows in two
places: `background` is a faint grey and `surface` is pure white, so cards lift
off the page without a heavy border; and the semantic colours are darkened to
carry small text, because a colour that reads well as a large block is usually
illegible as text on white. Every pair the interface uses is checked against
WCAG AA by `tests/unit/theme-contrast.test.ts`, which parses the stylesheet — so
a token changed without checking it fails there rather than in front of somebody.

### D-102 · Two layouts, because two jobs
**§11.5.** Staff work across thirty-odd screens all day, and a vertical sidebar
holds that many links in groups a person can scan. A student has a dozen pages
and visits a few, so they keep the top bar — a sidebar would spend a fifth of
their screen on links they do not use.

The sidebar groups by the job being done rather than by the system's structure:
"Users", "Students" and "Trainers" are three tables and one task, so somebody
hunting for a student need not know which screen owns them.

### D-103 · A navigation group label is not a heading
**§11.5, found by a test.** Marking the group titles as `<h2>` put "Courses and
batches" into the document outline, where it competed with the page's own `<h1>`
and met a screen-reader user again on every page. Binding them to the list with
`aria-labelledby` was worse: it gave the `<ul>` an accessible name, and a list
called "Courses and batches" then answered to a search for a form field named
"Batch". They are plain text. The grouping is visual; the links carry their own
names.

### D-104 · The test helper distinguishes "refused" from "never asked"
**§11.7.** A sign-in that produced no request at all was reported as a failed
sign-in, and sent people hunting for a permissions bug that was never there —
the click had landed on markup the development server had not finished
hydrating. The helper now retries when nothing reached the server, and only
reports a refusal when the server actually refused.

---

## Phase 12 — ERP foundation

### D-105 · The counsellor is a rung on the ladder, not a role beside it
**ERP §RBAC.** A counsellor's capability set is a strict subset of a manager's.
That was a choice, and the alternative — a set overlapping manager's without
being contained by it — would have been easier to write and quietly wrong.

`can_administer` decides who may touch whose account by comparing capability
sets. Two roles holding incomparable sets are a flat spot in the hierarchy:
neither can administer the other, for no reason anybody could explain from the
product. Containment keeps the rule statable in one sentence, and
`test_the_capability_ladder_has_no_ties` fails if a future change breaks it.

So the ladder is now superadmin ⊃ admin ⊃ manager ⊃ counsellor, with trainer and
student below it holding only the base set — they are not rungs, because their
reach comes from per-record assignment rather than from anything global.

### D-106 · A counsellor sets training up and does not run it
**ERP §Counsellor.** The line is drawn at the handover. Registration, course
choice, batch creation, timetabling, trainer assignment and enrolment are
admissions work and the role holds all of it. Attendance, DSR, assessment,
assignment, project, exam, completion and certification are not, and it holds
none of them — not even read access.

Nothing about accounts either. A counsellor creates student *records* through
the student service, which is a different act from administering an account:
they cannot edit, deactivate or re-role anybody, including students they
registered themselves.

The one that needed thinking about was reporting. A counsellor holds
`data.export` because admissions arrive and leave as spreadsheets, and does not
hold `report.view_any`, because the report catalogue aggregates the whole
institution and is a management tool. See D-107 for what that combination
exposed.

### D-107 · Exporting a report requires being allowed to read it
**ERP §RBAC, found by adding a role.** `ReportExportView` checked `data.export`
and nothing else, while the on-screen `ReportView` checked `can_read_reports`.
For four roles that difference was invisible, because every holder of
`data.export` also held `report.view_any`.

The counsellor is the first role to hold one without the other, and it turned a
latent inconsistency into a real hole: a file would have been a way to read a
report that the screen refuses. A file is not a weaker way to read something.
The export now applies both rules — read the report, and be allowed to export.

No existing role's behaviour changes, which is worth stating plainly: managers
and administrators pass both gates as before, and trainers were already refused
by the export capability. This is pure tightening.

### D-108 · The frontend capability list is checked against the backend, not trusted to match
**ERP §RBAC.** `lib/capabilities.ts` carried a comment saying it mirrored
`roles.py`. A comment cannot fail.

Drift there is quiet in the worst way: a capability string with a typo matches
nothing, so the control it guards is hidden from everybody, on every screen,
with no error anywhere — and nobody reports a button they have never seen.
`tests/unit/capability-mirror.test.ts` now parses the backend's own source and
checks both lists in both directions, along with the role list and its labels.
The backend file is the fixture, because a duplicated list is the thing being
guarded against.

### D-109 · The demo roster is derived, not counted
**ERP §RBAC.** `test_seed_is_idempotent` asserted `User.objects.count() == 29`.
Adding the counsellor to the seeded roster broke it, in a test whose subject is
whether a second run creates anybody — a question that has nothing to do with
how many accounts there are. It now compares against the roster the command
builds, so the next role to arrive changes one place instead of two.

Adding the counsellor to the seed itself was not optional: `verify_demo.sh` and
`test_seed_creates_an_account_for_every_role` both walk `UserRole.values`, on
the principle that a role nobody can sign in as is a role nobody exercises.
