# Architecture

This document records what the Phase 0 foundation is and, more importantly,
*why* each decision was made. Later phases should extend these patterns rather
than invent parallel ones.

---

## 1. Shape of the system

Four separated layers:

| Layer | Responsibility | Must not |
| --- | --- | --- |
| Frontend (Next.js) | Rendering, navigation, presentation state | Hold business rules or make authorization decisions |
| Backend API (Django + DRF) | Validation, authorization, business rules, persistence | Assume anything about which client is calling |
| Database (PostgreSQL) | Durable state, constraints, transactions | Be reachable directly from the frontend |
| Infrastructure (Docker, CI) | Reproducible environments, gates | Contain environment-specific secrets |

The frontend talks to the backend only through the documented HTTP API. There
is no shared code, no shared database access and no server-rendered Django
templates for application screens. The two halves can be deployed, scaled and
rolled back independently.

---

## 2. Repository layout

The layout follows the structure specified for the project, with two additions.

```
backend/
  config/            settings, root URLs, WSGI/ASGI
    settings/        base + hardened + one module per environment + guards
  apps/
    common/          cross-cutting building blocks
    accounts/        identity: user, roles, capabilities, auth flows
    students/        student profile domain   (Phase 1)
    trainers/        trainer profile domain   (Phase 1)
    courses/         catalogue and learning content (Phase 2)
    batches/         cohorts, schedules, conflict detection (Phase 3)
    enrollments/     participation and progress            (Phase 3)
    dashboards/      calendar and role dashboards          (Phase 3, no models)
    audit/           audit trail
    health/          liveness / readiness
  tests/             API and integration tests
frontend/
  app/ components/ lib/ hooks/ types/
  tests/ e2e/
infra/
  docker/ scripts/
docs/
.github/
```

### Why `audit` is its own app

The audit trail is written by *every* future module (enrollment, attendance,
grading, certificate issuance). Putting it in `common` would make `common`
depend on a database table and would blur the line between "helpers" and
"a domain with its own model, retention policy and admin". As a separate app it
has a stable import path (`apps.audit.services.record`), its own migration
history, and it can later be moved to a separate database or log sink without
touching callers.

### Why `health` is its own app

Health checks are an operational concern with their own URL namespace and their
own extension point (`READINESS_CHECKS`). Keeping them separate means adding a
Redis or worker probe is a one-line registry change in a file whose only job is
health, rather than an edit to a grab-bag module.

### Why `students` and `trainers` are separate apps

Both could have lived in `accounts` as extra models. They are separate because
they are separate *domains*: authentication data is small, stable and read on
every request, while profile data is large, mostly optional, and read only on
profile screens. Splitting them keeps the auth table small and means adding a
student field never touches the login path.

It also matches where the LMS is going. Phase 2's `Batch.trainer` foreign key
points at `trainers.TrainerProfile`, not at a user row that might be an
administrator; enrollments point at `students.StudentProfile`. Those
relationships are wrong to express against a generic user table.

### Why `courses` is one app, not three

Category, Course, Module, Lesson, Resource and VideoAsset are a single
aggregate: a lesson is meaningless without its module, a module without its
course. Splitting them across apps would buy circular imports and no boundary.

The boundary that *does* exist is not structural but a question — "who may see
or change this?" — and it lives in one file, `apps/courses/access.py`. Views
ask; they never decide. That matters because the same question is asked from
six places (catalogue listing, course page, lesson body, resource download,
video playback, editing), and six copies of the rule would drift apart.

### Why batches and enrolments are separate apps

Batch and schedule are the *delivery* side — they exist whether or not anyone
signs up, and the institution owns them. Enrolment is the *participation* side:
one student's relationship with a batch, which grows its own concerns (progress
now; attendance, results and certificates later).

The dependency runs one way — `enrollments → batches → courses` — so adding a
progress field never touches the timetable.

### Why `dashboards` owns no models

The calendar and the role dashboards answer "what should this person see right
now?", which is a presentation question rather than a domain one. Keeping it out
of the domain apps stops "what does the dashboard need?" leaking into models that
exist for other reasons, and every query still goes through the owning app's
access layer — so a dashboard can never become a way around a permission.

### Why a `services` layer

Business rules live in `apps/<app>/services.py`, not in serializers or views.

A rule enforced in a serializer only holds for requests that happen to use that
serializer. The same rule in a service holds for the API, the Django admin, a
management command, a data migration and a future background task. Phase 0
demonstrates the pattern with `accounts.services.create_user` and
`deactivate_user`: both wrap the write and its audit entry in one transaction.

Serializers keep exactly one job: validating and shaping data at the boundary.

---

## 3. Configuration and environments

Settings are split into:

```
config/settings/
  guards.py       boot-time assertions
  base.py         shared defaults — the secure ones
  hardened.py     the baseline for every network-reachable deployment
  local.py        developer machine / docker compose
  development.py  deployed development server
  staging.py      production-shaped, fake data
  production.py   strictest, fails closed
  test.py         pytest
```

Two rules make this safe:

1. **Defaults in `base.py` are the secure values.** Development relaxations
   (non-secure cookies, permissive hosts) live only in `local.py`. A forgotten
   override can therefore never weaken a deployed environment — the failure
   mode is "too strict", which is visible immediately.

2. **The environment is asserted at boot.** Each module calls
   `require_environment("<name>")`, which compares against the `DJANGO_ENV`
   variable supplied by the runtime. A process started with development
   settings against a production database refuses to start:

   ```
   ImproperlyConfigured: Environment mismatch: DJANGO_ENV='production' but
   config.settings.local was loaded.
   ```

Deployed environments additionally require, with no defaults:
`DJANGO_SECRET_KEY` (≥50 characters, ≥5 distinct, not a dev placeholder),
`DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`,
`DATABASE_URL` (PostgreSQL) and `CACHE_URL`.

---

## 4. API design

**Versioning.** URL path versioning (`/api/v1/`). It is visible in logs, easy to
route in a proxy and obvious to consumers. `ALLOWED_VERSIONS` is explicit, so an
unknown version is rejected rather than silently served. A breaking change ships
as `/api/v2/` while `v1` continues to work.

Health endpoints are deliberately **unversioned** (`/health/live/`,
`/health/ready/`): orchestrators and uptime monitors should not need
reconfiguring when the API version changes.

**Error format.** Every failure — validation, auth, throttling, 404, crash —
returns one envelope:

```json
{ "error": { "code": "…", "message": "…", "details": { }, "request_id": "…" } }
```

`code` is a stable machine-readable string clients may branch on; `message` is
written for a human; `details` carries field errors; `request_id` correlates
with server logs. Unhandled exceptions log a full traceback server-side and
return a generic message — internals never reach the client.

**Pagination.** Page-number pagination, `page_size` client-adjustable up to a
hard cap of 100 so a single request cannot become a full-table export. The
envelope (`count`, `page`, `page_size`, `total_pages`, `next`, `previous`,
`results`) is shaped so that endpoints over large append-only tables can later
switch to cursor pagination without breaking consumers that read `results`.

**Validation.** Layered: serializers reject malformed input at the edge
(`StrictSerializer` also rejects *unknown* fields, which surfaces client bugs
and attacker probing); model validators and database constraints back-stop code
paths that bypass the API.

---

## 5. Identity and authorization

The custom user model is created in Phase 0 because swapping `AUTH_USER_MODEL`
after tables exist is one of the hardest migrations in Django, and every future
LMS table will reference it.

- Email is the login identifier; a second unique "username" would be another
  thing to keep unique and support.
- UUID primary keys: identifiers appear in URLs, certificates and exports.
  Sequential integers would leak enrolment volumes and invite enumeration.
- A case-insensitive unique index on email prevents two accounts for one human.
- `role` on the user is the authoritative source for authorization. Django
  groups and permissions remain available for finer-grained rules on top.
- Users are deactivated, not deleted, so audit history stays attributable.

**Authentication strategy.** Session authentication for first-party browser
clients: `HttpOnly` cookies (unreadable by JavaScript, so XSS cannot exfiltrate
the credential), CSRF protection, and server-side revocation — deactivating a
user ends their access on the next request. The alternative, a JWT in
JavaScript-reachable storage, trades those properties for statelessness the LMS
does not need.

This requires the frontend and the API to share a registrable domain in
deployed environments (for example `app.grras.example` and
`api.grras.example`), so `SameSite=Lax` cookies are sent. That is a deployment
requirement, recorded here and in `docs/environments.md`.

Non-browser clients (a future mobile app, integrations) will need token
authentication. The foundation is ready for it — authentication classes are a
settings-level list — but no token code ships in Phase 0, because unused
authentication is unreviewed attack surface.

**Permissions: capabilities, not role checks.** Phase 1 replaced scattered role
comparisons with a capability matrix in `apps/accounts/roles.py`.

```python
ROLE_CAPABILITIES = {
    UserRole.ADMIN:   BASE | {USER_CREATE, USER_SET_ACTIVE, STUDENT_SET_FEE_STATUS, ...},
    UserRole.TRAINER: BASE,   # self-service only, in this phase
    UserRole.STUDENT: BASE,
}
```

Views declare what they *need*, not who is allowed:

```python
class UserListCreateView(ListCreateAPIView):
    permission_classes = (HasCapability,)
    capability_map = {"GET": Capability.USER_VIEW_ANY, "POST": Capability.USER_CREATE}
```

Two properties follow. Adding a fourth role — coordinator, accountant, parent —
is one entry in that table rather than an audit of every view. And a role with
no entry gets only the base self-service capabilities, so a half-finished role
fails closed.

`apps/common/permissions.py` also provides `IsActiveUser` (the project-wide
default, so endpoints are private unless they opt out), `IsOwnerOrHasCapability`
for object ownership, the `IsAdmin`/`IsTrainer`/`IsStudent` role classes where a
role genuinely is the subject, and `ReadOnly` as a composable modifier.

**Serializers are scoped by caller, not just by resource.** A student updating
themselves and an administrator updating that same student use *different*
serializer classes with different field lists. One serializer with conditional
field-stripping is where privilege-escalation bugs live. Combined with
`StrictFieldsMixin`, which rejects unknown fields rather than ignoring them,
sending `{"role": "admin"}` to a self-service endpoint returns 400 naming the
field — it cannot silently succeed.

---

## 3a. Rules a constraint cannot express

Three Phase 3 rules are relationships *between* rows, so none can be a column
check. Each is handled where it can be correct, and each has a test that attacks
it directly rather than through the happy path:

* **Capacity** is a count of other rows, so the batch is locked with
  `SELECT … FOR UPDATE` before the count is taken. Two threads racing for the
  last seat is a test, not an assumption.
* **One live enrolment per student per batch** *is* expressible: a **partial**
  unique index, unique only across live statuses, so re-enrolling after a
  cancellation stays legal. A test bypasses the service and asserts the database
  refuses the insert.
* **Schedule overlap** spans weekday, time and date range across two rows, and is
  checked in `apps/batches/conflicts.py` before every write.

---

## 4a. Content ordering and publishing

**Ordering is explicit.** Modules and lessons carry a `position`, and
`(parent, position)` is unique. Creation date is not an order: two lessons added
in the same second would tie, and reordering would mean rewriting timestamps.

The unique constraint is **deferred**, which is what makes reordering possible
at all — a reshuffle necessarily passes through states where two rows briefly
share a position, and a deferred constraint permits that inside one transaction
while still guaranteeing the end state is valid. Reorder endpoints require the
*complete* new order; a partial list would leave the remainder ambiguous.

**Publishing is a table, not scattered conditionals.** `services.TRANSITIONS`
declares which status may follow which, so an unreachable transition is a
data-integrity error rather than whichever view forgot to check. `IN_REVIEW`
exists and is reachable today — an assigned editor submits, an owner approves —
so making review mandatory later is a change to that table, not a migration.

---

## 5a. Human-readable identifiers

Records are keyed internally by UUID so nothing leaks from a URL, but people
need something they can read over a phone: `GRS-S-00042`, `GRS-T-00007`.

Courses get one too: `GRS-C-00013`. These are allocated from PostgreSQL
sequences (`apps/common/identifiers.py`)
rather than `MAX(id) + 1`, because sequence allocation is atomic and
non-blocking — two concurrent admissions can never receive the same number. Gaps
left by rolled-back transactions are expected and harmless.

---

## 6. Audit logging

`apps.audit.services.record(...)` is the entire public surface. Callers never
construct `AuditLog` rows directly, so redaction, actor resolution and request
metadata capture cannot be forgotten by a future module.

Each entry holds actor (and a denormalised label that survives account
deletion), action, resource type and id, result, timestamp, request id, client
IP, user agent, HTTP method and path, plus a scrubbed JSON context.

Records are append-only: `save()` refuses updates, `delete()` raises, and the
admin exposes them read-only. Retention trimming exists as one explicit,
greppable method (`purge_before`). An audit trail that can be quietly edited is
not evidence.

Audit writes never raise into the request path; a failure is logged at ERROR
instead. A safety net must not take down what it is protecting.

**Failure entries are written outside the request transaction.** This is not a
detail — it was a real defect found in Phase 1. `ATOMIC_REQUESTS` wraps each
request in a transaction, and DRF marks that transaction for rollback whenever
it converts an exception into an error response. A failure audit written inline
was therefore discarded by the very failure it recorded. `record()` now resolves
`durable=True` for any non-success result, queueing the entry for middleware to
write after the request transaction ends. Success entries still write inline, so
a record and the change it describes commit together or not at all.

Authentication events are captured through Django's `user_logged_in`,
`user_logged_out` and `user_login_failed` signals, so they are recorded no
matter which code path performs the login.

---

## 7. Observability

- **Request ids.** Every request gets one (a caller-supplied `X-Request-ID` is
  accepted only if it matches a strict pattern, so it cannot be used for header
  injection or log forging). It is echoed in the response, attached to every log
  line and stored on audit entries.
- **Structured logs.** JSON in deployed environments, human-readable locally. A
  redaction filter scrubs known-sensitive keys from structured context before
  anything is written.
- **Health checks.** `/health/live/` answers "is the process up?" without
  touching dependencies. `/health/ready/` runs the registered checks (currently
  database and cache) and returns 503 when any fails. Neither exposes hostnames,
  versions or configuration.
- **Error reporting.** Sentry is initialised only when `SENTRY_DSN` is set, with
  `send_default_pii=False` and request bodies never sent.

---

## 8. Frontend architecture

- **App Router** with server components by default; `'use client'` only where
  interactivity requires it (the status panel, error boundary).
- **One API client** (`lib/api.ts`). It resolves the base URL for the current
  execution context, always sends credentials, attaches the CSRF header on
  unsafe methods, applies a timeout, and converts the error envelope into a
  typed `ApiError`. Components never call `fetch` directly.
- **No business logic in components.** Components render state; `lib/` and
  `hooks/` handle transport and async state.
- **Shared states.** `LoadingState`, `ErrorState` and `EmptyState` exist as
  components so no screen quietly forgets one, and all three are consistent and
  accessible (`role="status"`, `aria-busy`, `role="alert"`).
- **Design tokens** are CSS custom properties in `globals.css`, including a dark
  scheme. A brand change is one edit, not a sweep through components.
- **UI primitives** (`components/ui/`) follow the shadcn/ui approach: the source
  lives in this repository and is owned by this project, rather than being an
  opaque dependency.

---

## 9. Testing strategy

| Level | Tool | Scope |
| --- | --- | --- |
| Backend unit | pytest | Models, managers, services, logging, middleware |
| Backend API | pytest + DRF test client | Auth flows, permissions, pagination, error envelope, audit |
| Configuration | pytest + subprocess | Production/staging settings load and pass `check --deploy` |
| Frontend unit | Vitest + Testing Library | API client, hooks, components, accessibility affordances |
| End-to-end | Playwright | Real browser against the real stack, including browser→API calls |

Backend tests run against real PostgreSQL — never SQLite — so constraints, JSON
fields and case-insensitive indexes behave as they will in production.
pytest-django creates a dedicated `test_*` database, wraps each test in a
transaction and rolls it back.

Configuration is tested like code: `tests/test_security_config.py` boots the
production and staging settings in a subprocess and asserts the resulting
security posture, catching deployment mistakes no request-level test would see.

---

## 10. Extension points for later phases

Everything below is prepared but not built, and none of it requires
restructuring the project:

| Need | Where it plugs in |
| --- | --- |
| New LMS domain (courses, batches, attendance…) | New app under `apps/`, model on `apps.common.models.BaseModel`, rules in `services.py`, routes registered in `config/api_urls.py` |
| A new role (coordinator, accountant, parent) | One entry in `ROLE_CAPABILITIES`; no view changes |
| A new permission | One `Capability` member, granted in the matrix, declared on the views that need it |
| Batch/course assignment for trainers | `TrainerProfile.is_accepting_assignments` and `skills` already exist for the "find an available trainer" query |
| Attendance | A row per `(schedule occurrence, enrolment)`; both sides already exist and are indexed |
| Assignments and results | Hang off `Enrollment`, which is why it is a first-class record rather than a join table |
| A new calendar feed | One function appended to `EVENT_SOURCES`; no view or component changes |
| Real video hosting | `VideoAsset.provider` already models S3 and managed services; the signed-URL call belongs in `LessonVideoPlaybackView` and nothing else changes |
| A new lesson content type | One `LessonContentType` member, one entry in `LESSON_CONTENT_REQUIREMENTS`, one branch in the renderer |
| A real fee ledger | A `payments` app owning amounts and transactions; `StudentProfile.fee_status` becomes derived rather than hand-set |
| Redis cache | `CACHE_URL` env var; `redis` service already in compose behind a profile |
| Celery workers | Redis broker as above; a worker service alongside it; tasks call the same services |
| New health dependency | Append a check function to `apps/health/checks.py::READINESS_CHECKS` |
| Object storage for uploads | `STORAGES["default"]` in settings; upload limits already configured |
| Token auth for mobile | Add an authentication class to `REST_FRAMEWORK` |
| Finer-grained permissions | Subclass `HasRole`, or use Django groups alongside the role field |
| Audit retention | `AuditLog.objects.purge_before(cutoff)` from a scheduled task |
