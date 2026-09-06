# Project implementation report

Audit date: 6 September 2026
Scope: the whole repository at commit `2a848bd` plus the uncommitted "Phase 11"
work present in the working tree.
Verification: full backend suite run (`1,339 passed, 2 skipped`, ~3m12s),
frontend unit suite run (`75 passed`, 16 files). End-to-end specs counted (82
across 13 files) but not executed — they need the full Docker stack running.

Companion document: `AUTHENTICATION_IMPLEMENTATION_REPORT.md` covers
authentication, authorization and audit in depth. This report covers everything
else and does not repeat it.

**Amended as the ERP phases land.** The audit itself is a snapshot of
6 September 2026; entries closed since then are struck through and marked with
the phase that closed them, so the original finding stays readable next to what
was done about it. The progress log is at the end of §17.

**Headline finding: this is not an early-stage project.** It is a substantially
complete LMS at "phase 10 / release readiness", with 26 Django apps, ~90 domain
models, 59 migrations, a full Next.js frontend of ~50 screens, 1,496 tests, and
a CI pipeline with six gates. The ERP requirements in the brief are best served
by **extending** it. The genuinely missing pieces are listed in §11 and they are
fewer than the brief assumes.

---

## 1. Architecture

| Layer | Technology | Notes |
| --- | --- | --- |
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework, django-filter, drf-spectacular | API-first, versioned at `/api/v1/` |
| Database | PostgreSQL 17 | SQLite refused at boot outside tests |
| ORM | Django ORM | No raw SQL in the request path |
| Frontend | Next.js 16 App Router, TypeScript, Tailwind CSS 4, shadcn/ui-style components | Client components with a single fetch wrapper |
| Auth | Django sessions + CSRF | See the authentication report |
| Cache / broker | Redis (compose profile) | Cache is mandatory in deployed environments |
| Background work | Celery worker + beat | Real worker, no result backend, `acks_late` |
| File storage | Pluggable: local disk or S3-protocol | Private ACL, signed short-lived URLs, boot guard against a public bucket |
| Email | SMTP with a DB outbox and retry sweep; credential mail sent inline | |
| Infrastructure | Docker, Docker Compose (dev + staging), nginx proxy, GitHub Actions | |
| Observability | Structured JSON logs, request ids, optional Sentry, `/health/live/` and `/health/ready/` | |

### Layering

The codebase follows one shape consistently, and it is a good one:

```
urls.py  ->  views.py  ->  serializers.py  ->  services.py  ->  models.py
                             (validation)      (business rules,   (data +
                                                audit, txn)        constraints)
                                  ^
                              access.py  (per-record authorization)
```

- **Business rules live in `services.py`, not in serializers or views.** A rule
  in a serializer only holds for requests that use that serializer; the same
  rule in a service also holds for the Django admin, management commands and
  future tasks. This is applied consistently across every app.
- **Per-record authorization lives in `access.py`** in each app
  (`courses`, `batches`, `sessions`, `assignments`, `assessments`, `projects`,
  `progress`, `questions`, `exams`, `announcements`, `discussions`,
  `reporting`). A trainer's authority comes from being assigned, not from a
  global capability, and that is resolved in one place per domain.
- **Every state change writes an audit entry inside its own transaction.**

### Settings

Five environment modules (`local`, `development`, `staging`, `production`,
`test`) over a shared `base` and a shared `hardened` baseline. `guards.py`
refuses to boot on an environment mismatch, a placeholder or weak secret,
SQLite, a missing shared cache, eager Celery, or a public S3 bucket. Secure
defaults live in `base`; relaxations live only in the development modules.

---

## 2. Existing modules

26 Django apps. Status against the brief's ERP requirements:

| App | What it does | Status vs. the ERP brief |
| --- | --- | --- |
| `common` | Base models, permissions, pagination, exceptions, throttling, uploads, scanning, storage, validators, logging, middleware, request context | **IMPLEMENTED** |
| `accounts` | User, roles/capabilities, auth, user administration | **IMPLEMENTED** — `COUNSELLOR` added in phase 12.1 |
| `audit` | Append-only audit log | **IMPLEMENTED** |
| `health` | Liveness/readiness with a check registry | **IMPLEMENTED** |
| `students` | `StudentProfile`, human ids (`GRS-S-00042`), fee status flag | **IMPLEMENTED** |
| `trainers` | `TrainerProfile`, human ids | **IMPLEMENTED** |
| `courses` | Category, Course, Module, Lesson, LessonResource, VideoAsset, CourseAssignment (authorship) | **IMPLEMENTED** (see §11 on "Topic") |
| `batches` | Batch, BatchSchedule, delivery mode, schedule-conflict detection | **IMPLEMENTED** |
| `enrollments` | Enrollment, LessonProgress | **IMPLEMENTED** |
| `sessions` | ClassSession (materialised from schedules), TrainerAssignmentHistory | **IMPLEMENTED** |
| `attendance` | AttendanceRecord with correction history and grouped percentage queries | **PARTIALLY_IMPLEMENTED** — status vocabulary differs from the brief |
| `assignments` | Assignment, attachments, submissions, submission files, grading | **IMPLEMENTED** |
| `assessments` | Assessment, AssessmentResult, ResultImport (CSV/XLSX preview→confirm) | **IMPLEMENTED** |
| `projects` | Project, StudentProject, ProjectFile, rubric review | **IMPLEMENTED** |
| `questions` | Question bank, six question types | **IMPLEMENTED** |
| `exams` | Exam, ExamSection, ExamAttempt, AttemptQuestion, AttemptAnswer, auto+manual marking | **IMPLEMENTED** |
| `progress` | CourseCompletion, progress reports, configurable completion rules, bulk helpers | **IMPLEMENTED** |
| `academics` | AcademicPolicy (thresholds, grade bands), AcademicEvent (calendar/holidays) | **IMPLEMENTED** |
| `certificates` | CertificateTemplate, Certificate, PDF rendering with QR, public verification | **IMPLEMENTED** |
| `notifications` | Notification, NotificationPreference, EmailMessage outbox, Celery tasks | **IMPLEMENTED** |
| `announcements` | Audience-scoped announcements with draft/publish/archive | **IMPLEMENTED** |
| `discussions` | Thread, Reply, batch-scoped, moderation | **IMPLEMENTED** |
| `learning` | LessonBookmark, LessonNote, continue-learning, batch directory | **IMPLEMENTED** |
| `reporting` | 10 reports, streaming CSV export, 9 metrics, admin dashboard, bulk import | **PARTIALLY_IMPLEMENTED** — CSV only, exports run inline |
| `dashboards` | Student dashboard, trainer dashboard, unified calendar (9 sources) | **PARTIALLY_IMPLEMENTED** — no manager or counsellor dashboard |
| **DSR** | — | **MISSING** entirely |

---

## 3. Existing database entities

~90 model classes across 59 migrations, 66 declared indexes and 23 unique
constraints, on top of Django's implicit FK indexes.

Mapping the brief's requested entity list to what exists:

| Brief entity | Exists as | Verdict |
| --- | --- | --- |
| User | `accounts.User` | Reuse |
| Role | `accounts.UserRole` (a column + code enum, not a table) | Reuse; see §8 |
| Permission | `accounts.Capability` + `ROLE_CAPABILITIES` (code, not a table) | Reuse; see §8 |
| Student | `students.StudentProfile` | Reuse |
| Trainer | `trainers.TrainerProfile` | Reuse |
| Counsellor | `accounts.UserRole.COUNSELLOR` (phase 12.1) | Reuse. No profile model: unlike a student or trainer, a counsellor has no domain record of their own |
| Manager / Admin | `UserRole.MANAGER` / `ADMIN` / `SUPERADMIN`, no profile model | Reuse |
| Course | `courses.Course` | Reuse |
| CourseModule | `courses.Module` | Reuse |
| CourseTopic | `courses.Lesson` | Reuse — "topic" and "lesson" are the same concept here. **Do not add a fourth level.** |
| Batch | `batches.Batch` | Reuse |
| BatchStudent | `enrollments.Enrollment` | Reuse |
| BatchTrainer | `batches.Batch.trainer` + `sessions.TrainerAssignmentHistory` | Reuse |
| ClassSession | `sessions.ClassSession` | Reuse |
| AttendanceRecord | `attendance.AttendanceRecord` | Reuse, extend statuses |
| DSR | — | **Create** |
| Assessment | `assessments.Assessment` | Reuse — already reusable entities with per-assessment `max_marks`, exactly as the brief asks |
| AssessmentResult | `assessments.AssessmentResult` | Reuse |
| Assignment | `assignments.Assignment` | Reuse |
| AssignmentSubmission | `assignments.AssignmentSubmission` | Reuse |
| Project | `projects.Project` | Reuse |
| StudentProject | `projects.StudentProject` | Reuse |
| Feedback | — (free-text feedback fields exist on submissions, results and project reviews) | **Create** if a first-class, queryable feedback record is wanted |
| PerformanceReview | — | **Create** |
| Notification | `notifications.Notification` | Reuse |
| AuditLog | `audit.AuditLog` | Reuse |
| ExportJob | — (exports are synchronous streams) | **Create** |
| File | — (per-domain: `LessonResource`, `AssignmentAttachment`, `SubmissionFile`, `ProjectFile`) | Reuse the per-domain models; a unified `File` is not worth the migration |
| SystemSetting | `academics.AcademicPolicy` covers academic rules only | **Create** for non-academic settings, or extend `AcademicPolicy`'s pattern |

### Key modelling decisions already made (and worth keeping)

- **UUID primary keys everywhere.** Ids appear in URLs, certificates and
  exports; sequential integers would leak enrolment counts.
- **Attendance is keyed on `(ClassSession, Enrollment)`, not `(session,
  student)`** — the same person can take the same course twice in different
  batches, and those are separate histories. A unique constraint
  (`attendance_one_per_session_enrollment`) enforces exactly the
  "prevent duplicate attendance" rule the brief asks for.
- **Attendance corrections keep the previous value** (`previous_status`,
  `corrected_by`, `corrected_at`, `correction_reason`) rather than overwriting.
- **Class sessions are materialised rows, not derived occurrences**, so
  attendance survives a schedule edit.
- **Assessments are reusable entities with their own `max_marks`** — there are
  no `assessment_1`, `assessment_2` columns anywhere. The brief's warning is
  already heeded.
- **Completion thresholds live in `AcademicPolicy`, not in code.** The brief's
  "do not hardcode thresholds" requirement is already met for the completion
  rules; it is not yet met for a *risk* engine, because there isn't one.

---

## 4. Existing APIs

Every route is registered in one reviewable file, `backend/config/api_urls.py`.
Mounted namespaces under `/api/v1/`:

`auth/`, `users/`, `students/`, `trainers/`, `categories/`, `courses/`,
`modules/`, `lessons/`, `resources/`, `batches/`, `schedules/`, `sessions/`,
`attendance/`, `enrollments/`, `progress/`, `assignments/`, `submissions/`,
`assessments/`, `results/`, `projects/`, `questions/`, `exams/`, `attempts/`,
`completions/`, `certificates/`, `verify/` (public), `academics/`,
`notifications/`, `announcements/`, `discussions/`, `learning/`, `reports/`,
`dashboards/`, `imports/`, `calendar/`, `dashboard/`.

Cross-cutting API properties, all already in place:

- **Pagination** — `DefaultPagination`, page size 25, hard cap 100,
  `stable_order()` appends the pk to every ordering so a row cannot appear on
  two pages (a real bug that was found and fixed).
- **Filtering / search / ordering** — `DjangoFilterBackend`, `SearchFilter`,
  `OrderingFilter` are DRF defaults here; filtersets name explicit fields, so a
  client cannot craft an expensive lookup.
- **One error envelope** — `{error: {code, message, details, request_id}}` for
  every failure including 500s, with no stack traces or internals.
- **Throttling** — `anon` 60/min, `user` 600/min, `auth` 10/min,
  `burst` 20/min (exports and imports), `certificate_verification` 30/min.
- **OpenAPI schema** via drf-spectacular, with enum name overrides so the
  generated client is stable.
- **Versioning** — `URLPathVersioning`, `ALLOWED_VERSIONS = ['v1']`.

---

## 5. Existing pages

~50 routes in `frontend/app/`.

**Public / auth:** `/`, `/login`, `/forgot-password`, `/reset-password`,
`/verify-email`, `/verify/[code]` (public certificate verification), `/status`.

**Student:** `/dashboard`, `/my-learning`, `/courses`, `/courses/[slug]`,
`/courses/[slug]/learn/[lessonId]`, `/my-batches`, `/my-assignments`,
`/my-projects`, `/exams`, `/exams/[examId]`, `/attempts/[attemptId]`,
`/my-results`, `/my-attendance`, `/my-progress`, `/calendar`,
`/announcements`, `/discussions`, `/discussions/[threadId]`, `/notifications`,
`/profile`, `/settings/account`, `/settings/security`.

**Trainer:** `/teaching` (classes today), `/teaching/sessions/[sessionId]`,
`/teaching/assignments` + `[assignmentId]`, `/teaching/assessments` +
`[assessmentId]`, `/teaching/projects` + `[projectId]`, `/teaching/exams` +
`[examId]`, `/teaching/questions`.

**Admin:** `/admin/overview`, `/admin/users` + `[userId]` (new, uncommitted),
`/admin/students`, `/admin/trainers`, `/admin/courses` + `[courseId]`,
`/admin/categories`, `/admin/batches` + `[batchId]`, `/admin/academics`,
`/admin/completions`, `/admin/certificates`, `/admin/reports`, `/admin/imports`.

**Error boundaries:** `app/error.tsx`, `app/loading.tsx`, `app/not-found.tsx`.

---

## 6. Existing dashboards

| Dashboard | Where | Content |
| --- | --- | --- |
| Student | `apps/dashboards/views.py::StudentDashboardView` → `/dashboard` | Enrolments, progress, upcoming classes, pending work, results |
| Trainer | `apps/dashboards/views.py::TrainerDashboardView` → `/dashboard` | Today's classes, batches, pending grading |
| Admin | `apps/reporting/dashboards.py::admin_dashboard` → `/admin/overview` | Scoped counts, capability-gated |
| Trainer workload | `apps/reporting/dashboards.py::trainer_workload` | Batches, students, pending work per trainer |
| Batch summaries | `apps/reporting/dashboards.py::batch_summaries` | One grouped query, capped at 20 |
| Unified calendar | `apps/dashboards/calendar.py` | Nine event sources, each resolving its own access |

Dashboard queries have **asserted query-count ceilings** in
`tests/test_reporting.py` and `tests/test_performance.py` — the batch dashboard
was profiled from 4,097 queries down to 18ms.

**Missing: a manager dashboard and a counsellor dashboard.** The brief specifies
both in detail. `admin_dashboard` is scoped by capability and a manager can
reach it, but it is not the manager-specific view the brief describes (no
attendance alerts, no DSR status, no student-risk list, no pending reviews).

---

## 7. Existing reusable components, hooks, services and utilities

**Do not rebuild any of these.**

### Frontend components (`frontend/components/`)

`app-shell.tsx` (staff sidebar + student top bar; heavily rewritten in the
uncommitted work), `navigation.ts` (new — the nav registry, capability- and
role-driven), `auth-provider.tsx`, `require-auth.tsx`, `list-toolbar.tsx`
(search + filters + page size), `pagination.tsx`, `states.tsx`
(`LoadingState`, `EmptyState`, `ErrorState`, skeletons), `calendar-view.tsx`,
`schedule-list.tsx`, `course-card.tsx`, `lesson-content.tsx`,
`progress-bar.tsx`, `progress-rules.tsx`, `profile-image-field.tsx`, and
`ui/{alert,badge,button,card,field,input,skeleton,table}.tsx`.

### Frontend hooks

- `hooks/use-list.ts` — drives every server-paginated list: page, search,
  ordering, filters all become query parameters; a filter change resets to page 1;
  request identity is tracked so a stale response cannot overwrite a newer one.
- `hooks/use-api.ts` — single-resource fetching with loading/error state.

### Frontend API layer (`frontend/lib/`)

One client (`api.ts`) and one typed module per domain: `auth`, `people`,
`courses`, `batches`, `academics`, `assessments`, `assignments`, `projects`,
`progress`, `exams`, `communication`, `reporting`, plus label helpers
(`labels`, `course-labels`, `batch-labels`, `academic-labels`), `capabilities`,
`env`, `utils`. **A second API client would be a duplication.**

### Backend shared services (`backend/apps/common/`)

`models.py` (`BaseModel`), `permissions.py`, `pagination.py`
(`DefaultPagination`, `stable_order`), `exceptions.py`, `throttling.py`,
`serializers.py` (`StrictSerializer`, `StrictModelSerializer`, `SafeCharField`),
`validators.py`, `uploads.py` (allowlist + magic-byte pairing + re-encode +
inert `.bin` storage), `scanning.py` (fail-closed malware hook), `storage.py`
(local/S3 abstraction + boot guard), `identifiers.py` (human-readable id
sequences), `logging.py` (`scrub`, `RedactSecretsFilter`, `JSONFormatter`),
`middleware.py`, `request_context.py`, `mixins.py`.

### Management commands

`seed_demo_data`, `seed_courses`, `seed_batches`, `seed_academics`,
`seed_scale_data` (400 students / 16k attendance / 3.2k results),
`send_pending_email`.

---

## 8. Technical debt

Ordered by how much it will cost the ERP work.

**T1 — Capabilities are code, not data.** `ROLE_CAPABILITIES` is a Python
constant. Adding a role or re-mapping one requires a deploy. This is a
deliberate, documented decision and it is defensible (a table is another thing
to keep consistent, and the matrix is covered by a 160-test sweep). But the
brief asks for admin-managed "Roles" and "Permissions" screens, which this
cannot serve without a schema change. **Decide explicitly** before building
those screens: either accept read-only role/permission screens, or introduce a
`RolePermission` table that seeds from the current matrix.

**T2 — No soft delete anywhere.** No model has `deleted_at`, `deleted_by` or
`delete_reason`. The pattern used instead is a status enum with an `ARCHIVED`
member (courses, batches, assignments, assessments, projects, exams,
announcements) and `is_active` for users. That is a reasonable substitute for
*business* archival but does not give the brief's admin-recovery/recycle-bin
behaviour, and hard `DELETE` endpoints do exist for some records
(modules, lessons, questions, replies). This is the single largest
cross-cutting change the brief requires.

**T3 — Redis is present but the application caches nothing.** The only
`cache.get`/`cache.set` in `apps/` is the health check's round-trip probe
(`apps/health/checks.py:88`). Throttle counters and sessions use it implicitly.
Dashboard aggregates, permission resolution, course lists and configuration are
all recomputed per request. The infrastructure is there; the usage is not.

**T4 — Exports and imports run inside the HTTP request.** `stream_csv` is a
generator over a `StreamingHttpResponse`, so memory is bounded and the design is
sound — but the request still holds a worker for the duration, and the only
protection is `BurstThrottle` at 20/min. There is no `ExportJob`, no status
lifecycle, and no way to hand a user a link to a finished file. Result imports
are the same (documented as a known limitation: "Import runs inline, not
queued").

**T5 — `revoke_sessions` is an O(all sessions) scan.** Detailed in the
authentication report (W4). It is called on every deactivation, role change,
email change and password reset.

**T6 — No cursor pagination for append-only tables.** The audit log and activity
feeds use page-number pagination. `pagination.py`'s docstring flags this and the
response envelope was shaped to make the switch backwards-compatible. Deep
paging into the audit log will get slow.

**T7 — XLSX export is not built.** Import accepts CSV *and* XLSX; export emits
CSV only. Certificates render PDF (ReportLab is a dependency), so a PDF path
exists but is not generalised to reports.

**T8 — `docs/RELEASE_READINESS.md` is stale on CI.** It states "CI has never
executed — no git remote". A remote now exists (`vidyansh07/lmsSchool`) with
three open Dependabot PRs (eslint 9→10, Django 5.2.17→6.1, reportlab 4→5).
Those are major-version bumps and should be triaged deliberately — **do not
merge the Django 6.1 bump as part of ERP feature work.**

**T9 — Seven end-to-end specs fail on staging.** Recorded honestly in
`RELEASE_READINESS.md` as specs still coupled to the development stack. Not
product bugs, but they weaken the staging gate.

**T10 — Uncommitted work in the tree.** The Phase 11 changes (role hierarchy,
user detail screen, light-only theme, navigation rework, four new test files)
are complete and green but not committed. Commit them before starting new work
so the ERP changes are reviewable on their own.

---

## 9. Security issues

The full security posture is in the authentication report. Repository-wide, the
outstanding items are:

| Issue | Severity | Note |
| --- | --- | --- |
| No MFA | Medium-high | No second factor for any role, including `superadmin` |
| Per-IP-only login rate limiting | Medium | No per-account limit, no lockout |
| `SameSite=Lax` topology constraint | Medium, latent | Undocumented; breaks auth if the API moves to a different registrable domain |
| Unbounded `revoke_sessions` | Medium | Self-inflicted DoS risk at scale |
| Reset tokens in the URL query string | Low-medium | Mitigated by 1-hour TTL and single use; no explicit `Referrer-Policy` on the frontend |
| PBKDF2 rather than Argon2id | Low | Django default; `argon2-cffi` not installed |
| No malware scanner configured | Low | The hook exists and fails closed; `UPLOAD_SCANNER=disabled` |
| Local file storage in staging | Low | S3 wiring is complete; no bucket provisioned |

**Checked and clear:** IDOR (object-level checks resolve ownership from the
object; `test_authorization_matrix.py` covers cross-tenant cases), mass
assignment (strict serializers, per-caller field lists), SQL injection (ORM
only), XSS (JSON-only API, CSP with a per-request nonce on the frontend), CSRF
(enforced including on anonymous POSTs), file upload (extension + magic-byte
pairing, re-encoding, inert `.bin` storage, `octet-stream` attachment
responses, sandbox CSP, download authorization), export authorization (exports
run on the same scoped queryset as reports, with a separate `data.export`
capability), formula injection (neutralised both on import and on export),
security headers (asserted in `e2e/hardening.spec.ts` against the running
stack), database least-privilege (`infra/db/least-privilege.sql`, 21 tests).

---

## 10. Performance

### Already done, and done well

- **N+1 elimination** with measured before/after: `student_progress` 7,400 → 42
  queries; batch dashboard 4,097 → 18ms; enrolment list 34 → 9 queries; the
  project list N+1 was found and fixed.
- **Query-count ceilings asserted as tests** (`tests/test_performance.py`, 27
  tests) so a regression fails CI rather than a user's afternoon.
- **Grouped aggregate helpers** instead of per-row queries —
  `attendance_summaries(enrollment_ids)` is the model: every requested id
  appears in the result, including students with no records, so no caller
  writes a "missing means zero" branch.
- **Reports iterate with `.iterator()` and chunking**; exports stream.
- **`select_related` / `with_related()` querysets** on every list view.
- **Profiled at 400 students / 16k attendance rows / 3.2k results**
  (`seed_scale_data`).
- **Deterministic pagination** (`stable_order`).
- **Frontend:** server-side pagination and filtering everywhere via `useList`;
  one page in memory at a time; request-identity tracking prevents stale
  overwrites.

### Remaining performance gaps

| Gap | Impact |
| --- | --- |
| No application-level caching (T3) | Dashboards and configuration recomputed per request |
| Exports/imports inline (T4) | A large export holds a worker |
| `revoke_sessions` full scan (T5) | Slow, unbounded, inside `ATOMIC_REQUESTS` |
| Page-number pagination on the audit log (T6) | Deep paging degrades |
| No frontend request cache/dedupe | `useList` and `useApi` refetch on every mount; no SWR/React Query layer, so navigating back re-requests. No duplicate-request suppression |
| No virtualisation on long tables | Fine at page size 100; would matter if bulk screens raise it |

---

## 11. Gap analysis against the ERP brief

This is the actionable list. Everything not named here already exists.

### MISSING — must be built

| # | Gap | Notes |
| --- | --- | --- |
| G1 | **DSR (Daily Status Report)** | No model, no API, no screen, no reference anywhere in the repo. The brief specifies ~25 fields and a 6-state workflow (DRAFT → SUBMITTED → UNDER_REVIEW → APPROVED / REJECTED / REVISION_REQUIRED). Entirely new. Natural home: a new `apps/dsr` keyed on `(ClassSession)` or `(Batch, date)`, reusing `ClassSession` for the class and `attendance_summaries` for the counts |
| G2 | ~~`COUNSELLOR` role~~ and its workflow | **Role closed in phase 12.1** — and the API half of the workflow proved to need no new endpoints at all, which the phase's tests demonstrate by driving registration, batch creation, trainer assignment and enrolment through the existing ones. What remains is the *interface*: the fast single-screen flow, bulk student import into a batch, student/batch transfer, and duplicate detection on single registration |
| G3 | **Soft delete + restore + admin recovery** | No `deleted_at`/`deleted_by`/`delete_reason` on any model; no default-manager filtering; no restore endpoints; no recycle-bin screen. Cross-cutting: needs a `SoftDeleteModel` base in `apps/common/models.py`, a default manager, and a migration per adopting model |
| G4 | **Export jobs** | No `ExportJob` model, no QUEUED/PROCESSING/COMPLETED/FAILED lifecycle, no background execution. Celery is already running and `stream_csv` already exists — this is a wrapper, not a rewrite |
| G5 | **Excel and PDF export** | CSV only today. `openpyxl` is already a dependency (used by the importer) and `reportlab` is already used for certificates |
| G6 | **Manager dashboard** | The brief specifies 15 widgets. `admin_dashboard`, `trainer_workload` and `batch_summaries` supply several of the underlying figures already |
| G7 | **Counsellor dashboard** | Nothing exists |
| G8 | **Performance / risk engine** | `progress/rules.py` computes *completion* rules against configurable thresholds; there is no *risk* engine (attendance risk, academic risk, assignment risk, progress risk) and no composite student performance score. `rules.py` is the right pattern to copy, and `AcademicPolicy` is the right place for the thresholds — the brief's "do not hardcode thresholds" is achievable by extension |
| G9 | **Composite trainer performance** | `reports.trainer_activity` covers batches, students and some counts. Missing: attendance submission rate, DSR submission/approval rate, assessment/assignment/project completion rates, manager rating, pending and overdue work |
| G10 | **`Feedback` and `PerformanceReview` entities** | Free-text feedback fields exist on submissions, results and project reviews, but there is no queryable "manager gave this trainer feedback" record |
| G11 | **Course timeline: planned vs actual** | `Course → Module → Lesson` exists and `ClassSession` has `status` and a free-text `topic`, but there is no link from a session to the lesson/topic it covered, so "is this batch ahead or behind schedule?" cannot be answered. This is a **small, high-value addition**: an FK from `ClassSession` to `Lesson` (planned and actual) plus a per-topic status |
| G12 | **Attendance status vocabulary** | Today: `PRESENT`, `ABSENT`, `LATE`, `EXCUSED`. The brief wants `PRESENT`, `ABSENT`, `ONLINE`, `OFFLINE`, `LEAVE`, `OTHER`. Note `Batch.delivery_mode` and `Enrollment.effective_delivery_mode` already model online/offline as a *property of the enrolment*, which is arguably better than a per-day attendance status. **Resolve this deliberately** — adding ONLINE/OFFLINE as attendance statuses alongside the existing delivery mode would create two sources of truth |
| G13 | **`SystemSetting`** | `AcademicPolicy` covers academic rules. Non-academic platform settings have no home |
| G14 | **UX speed features** | No global search, no command palette, no keyboard shortcuts, no multi-select/bulk actions on tables, no inline editing, no saved filters, no date shortcuts, no autosave (except the exam attempt), no undo. `list-toolbar.tsx` and `useList` are the right foundations |

### PARTIALLY_IMPLEMENTED — extend, do not rebuild

| Area | What exists | What is missing |
| --- | --- | --- |
| RBAC | Full capability matrix, four-rung ladder, 160-test sweep, counsellor role and the DSR/performance/export capabilities (phase 12.1) | Organisational scoping — a manager still sees the whole institution |
| Attendance | Records, corrections with history, unique constraint, grouped percentages, bulk marking, CSV import | Status vocabulary (G12); no "today's class workspace" |
| Exports | 10 reports, streaming CSV, scoped querysets, separate capability | Jobs, formats, background execution |
| Dashboards | Student, trainer, admin, calendar | Manager, counsellor |
| Imports | Preview → confirm, all-or-nothing, formula refusal, duplicate and unknown-student detection, audit record, full error report | Only students and attendance; no batch/trainer/result-by-batch importers |
| Validation | Strict serializers, `SafeCharField`, control-character and phone/name validators, upload validation, server-side mark bounds | Nothing structural missing |
| Null handling | The API returns explicit `null`s and the frontend has `states.tsx` + label helpers | Not systematically audited against the brief's "never show undefined/NaN/Invalid Date" rule; no shared formatter for dates/percentages with fallbacks |
| Caching | Redis running, mandatory in deployment | No application caching (T3) |

### BROKEN

**None found.** The backend suite is green (1,339 tests) including the
uncommitted work, and the frontend unit suite is green (75 tests). The seven
staging-only e2e failures (T9) are environment coupling in the specs, documented
as such, not product defects.

---

## 12. Missing indexes, validation, error handling, null handling, logging

Assessed specifically, because the brief asks.

**Indexes.** 66 explicit `models.Index` declarations plus 23 unique constraints,
on top of Django's implicit FK indexes. Two migrations exist purely to *drop*
redundant FK indexes (`announcements/0002`, `assessments/0003`,
`assignments/0003`, `exams/0004`, `projects/0003`), which means index hygiene has
been actively reviewed rather than accreted. Composite indexes match the actual
query shapes (`user(role, is_active)`, `attendance(enrollment, status)`,
`attendance(session, status)`, `audit(resource_type, resource_id)`,
`audit(actor, -created_at)`, `audit(action, -created_at)`). **No missing index
was identified.** New entities (DSR, ExportJob) will need their own.

**Validation.** Comprehensive. `StrictSerializer` rejects unknown fields by
name; `SafeCharField` and `validate_no_control_characters` sanitise text; marks
are bounded server-side; upload validation pairs extension against magic bytes;
external assessment links are https-only; ids are UUID-typed in URL patterns
(`<uuid:...>`), so a malformed id 404s at routing. **Gap:** query parameters are
validated by filtersets where a filterset exists; a few hand-written views read
`request.query_params` directly — worth a sweep, but no exploitable case was
found.

**Error handling.** Centralised and complete: one envelope, machine-readable
codes, field errors, request id, no stack traces, generic 500s. `ApplicationError`
/ `ConflictError` / `AuthorityError` give services a typed vocabulary. Frontend
has `ApiError`, `fieldErrors()`, `errorMessage()` and route-level `error.tsx`.
**No gap.**

**Null handling.** The API is explicit about nulls (`percentage: None` when
there are no sessions, rather than `0`). The frontend has `EmptyState` and label
helpers. **Gap:** there is no shared, tested formatter enforcing the brief's
"Not Available / Not Assigned / Not Submitted / No Data / Unknown" fallbacks, and
no test asserting that `undefined`, `NaN` or `Invalid Date` never render. That
is worth adding as a small utility plus a unit test, given how much new UI is
coming.

**Logging.** Structured, with request-id correlation, JSON in deployed
environments, dedicated `grras.security` / `grras.audit` / `grras.calendar`
channels, and a `RedactSecretsFilter` on the handler. Audit writes are scrubbed
at the single write point. **Gap:** no alerting or aggregation is wired — the
audit log records brute-force patterns that nothing acts on — and no retention
job is scheduled (`purge_before` exists but nothing calls it).

---

## 13. Existing tests

| Suite | Count | Command |
| --- | --- | --- |
| Backend (pytest) | **1,339 passing**, 2 skipped, ~91% statement coverage | `DJANGO_ENV=test pytest` (needs PostgreSQL) |
| Frontend unit (vitest) | **75 passing**, 16 files | `npm run test` |
| End-to-end (Playwright) | **82 specs** across 13 files | `npx playwright test` (needs the full stack) |
| Release journey | 1 spec, 23 steps | `E2E_RELEASE_JOURNEY=1 npx playwright test --project=release` |

Backend coverage by area: auth (17), password flows, email verification,
authorization matrix (160 route×role), permissions, role hierarchy (new),
user admin, students, trainers, courses (+ security + access-by-enrolment +
resources), batches, schedule conflicts, enrolments (+ security), class sessions
(23), attendance (21), assignments (36) + assignment files (31), assessments
(23), result import (26), academic config (20), projects (38), question bank
(19), exams (35, including nine named failure modes and a threaded
concurrent-start test), progress and completion (35), certificates (28),
notifications (25), learning and discussions (22), reporting (60), performance
(27), background work (14), file storage security (21), database security (21),
data and audit security (31), errors, health, audit, seeds, smoke.

**Notable:** query-count ceilings, a threaded concurrency test, and a threaded
health-probe race test are all asserted as tests. That is unusual and worth
preserving.

**Gaps relative to the brief's test list:** no tests for DSR, exports-as-jobs,
soft delete or restore (none of which exist yet). Edge cases the brief names —
missing/deleted student, deleted batch, duplicate attendance, invalid marks,
missing trainer, unauthorized manager/trainer, empty batch, empty export, large
dataset, invalid import file — are **already covered** across
`test_authorization_matrix.py`, `test_result_import.py`, `test_performance.py`
and the per-domain suites.

---

## 14. CI/CD

`.github/workflows/ci.yml`, six jobs gated by a `ci-passed` aggregator:

1. **backend** — ruff format check, ruff lint, migration drift check, pytest with
   coverage, `manage.py check --deploy` against production settings.
2. **backend-security** — bandit, pip-audit.
3. **frontend** — eslint, `tsc`, vitest, production build, npm audit.
4. **secret-scan** — gitleaks over the working tree *and* history.
5. **docker-build** — both production images.
6. **e2e** — starts the stack, waits for readiness, seeds demo/course/batch data,
   runs Playwright, collects logs on failure, tears down.

`make` targets mirror every CI step, so "green locally" and "green in CI" mean
the same thing. Dependabot is configured. **Note T8:** the docs still claim CI
has never run; a remote now exists.

---

## 15. Environment configuration, seeds, migrations, backups

- **Environments:** `.env.example`, `.env.staging.example`,
  `.env.production.example` are tracked; real `.env` files are git-ignored.
  Boot guards make a cross-environment mistake impossible rather than unlikely.
- **Seeds:** `seed_demo_data`, `seed_courses`, `seed_batches`, `seed_academics`,
  `seed_scale_data`. All refuse to run where `ALLOW_DEMO_SEED` is false, use
  reserved fake domains, and converge on repeat runs. Covered by 16 tests.
- **Migrations:** 59, verified non-destructive by `scripts/check_migrations.sh`;
  fresh install and reverse-then-reapply both verified. Drift is checked in CI.
- **Backups:** `scripts/backup.sh` with `--verify`; restore into a scratch
  database verified including sequences. Object storage is not backed up (no
  bucket provisioned).
- **Staging:** `docker-compose.staging.yml` — gunicorn, `DEBUG=False`, hardened
  settings, TLS via nginx, Celery worker + beat, Redis, PostgreSQL 17,
  S3-protocol object storage (MinIO).

---

## 16. Recommended sequencing

The brief's 14 phases, re-scoped against what already exists. Phases 1–10 of the
brief are largely *already done*; what follows is what actually remains.

| Step | Work | Depends on |
| --- | --- | --- |
| **0** | Commit the Phase 11 tree. Triage the three Dependabot PRs separately (do not take Django 6.1 mid-feature) | — |
| ~~**1**~~ | ✅ **Done (phase 12.1).** `COUNSELLOR` in `UserRole` + `ROLE_CAPABILITIES` + `lib/capabilities.ts` + the matrix sweep; the DSR, performance and export capabilities declared ahead of the features that consume them; report export tightened; the capability mirror made a test | — |
| **2** | Soft-delete foundation: `SoftDeleteModel` in `apps/common/models.py`, default manager, restore service + audit actions, admin recovery endpoints. Adopt it model by model, migration by migration | 1 |
| **3** | DSR: new `apps/dsr` — model keyed on `ClassSession`, 6-state workflow, trainer submit / manager review services, access layer, API, tests | 1 |
| **4** | Course timeline: FK from `ClassSession` to `Lesson` (planned + actual) and per-topic status; planned-vs-actual progress in `apps/progress/reports.py` | — |
| **5** | Attendance status decision (G12) and, if adopted, the migration + percentage-rule update | — |
| **6** | Counsellor workflow screens: fast registration, batch creation/selection, bulk assignment, transfer, duplicate detection. Almost entirely frontend over existing APIs | 1 |
| **7** | Trainer "today's class" workspace: one screen over `ClassSession` + attendance + DSR + assessment + assignment | 3 |
| **8** | Performance/risk engine in the `progress/rules.py` shape, thresholds in `AcademicPolicy`; composite trainer performance | 3, 4 |
| **9** | Manager and counsellor dashboards over the engine | 8 |
| **10** | `ExportJob` + Celery execution + XLSX/PDF writers, wrapping the existing report producers | — |
| **11** | Caching pass: dashboard aggregates, configuration, permission resolution, with explicit invalidation on mutation | 9 |
| **12** | UX speed pass: global search, command palette, bulk actions, saved filters, inline editing | 6, 7 |
| **13** | Hardening: per-account rate limit, bounded session revocation, MFA for admin roles, null-handling formatter + test, audit retention job | — |

Each step is additive. None requires replacing existing authentication,
database architecture, API architecture, UI components or working features.

---

## 17. Completion percentage

Scored as "an ERP matching the brief", not as "an LMS".

| Area | % | Basis |
| --- | --- | --- |
| Platform foundation (settings, guards, health, errors, logging, request context) | 100% | Complete, tested, hardened |
| Authentication | 90% | See the authentication report |
| Authorization / RBAC | 95% | Five roles on a proven-monotonic ladder plus two scoped roles; −5 for no organisational scoping |
| Audit logging | 95% | Append-only, scrubbed, comprehensive; no retention job or alerting |
| User / student / trainer management | 95% | Full CRUD, admin screens, per-user audit view |
| Course catalogue and content | 95% | Categories, courses, modules, lessons, resources, video metadata, authorship |
| Batches, schedules, enrolment | 95% | Including conflict detection and capacity races |
| Class sessions | 90% | Materialised, reschedulable, trainer history; not yet linked to topics |
| Attendance | 75% | Model and API are strong; status vocabulary unresolved; no fast marking workspace |
| **DSR** | **0%** | Does not exist |
| Assessments and results | 95% | Reusable entities, per-assessment max marks, CSV/XLSX import with preview |
| Assignments | 95% | Full lifecycle with file security |
| Projects | 95% | Full lifecycle with rubric review |
| Question bank and exams | 95% | Six question types, frozen papers, server clock, nine failure modes tested |
| Progress and completion | 90% | Configurable rules; no risk engine |
| Certificates | 95% | Issue, reissue, revoke, PDF+QR, public verification |
| Notifications and communication | 90% | In-app, email outbox, announcements, discussions; no push (declined) |
| Reporting | 75% | 10 reports, 9 metrics, scoped querysets; CSV only, inline |
| Imports | 80% | Excellent preview→confirm machinery; only two importers |
| **Exports as jobs** | **0%** | No `ExportJob`, no background execution |
| Dashboards | 60% | Student, trainer, admin, calendar; no manager, no counsellor |
| **Performance / risk engine** | **20%** | Completion rules exist and are the right pattern; risk scoring does not |
| **Soft delete / restore** | **10%** | `ARCHIVED` statuses and `is_active` only |
| Caching | 15% | Infrastructure in place, application usage absent |
| API scalability | 90% | Pagination, filtering, stable ordering, capped page size, N+1 eliminated, profiled at scale |
| Frontend screens | 80% | ~50 screens covering student, trainer and admin; no counsellor, no manager |
| Frontend UX speed features | 25% | Server-side lists, filters and toolbars; no palette, search, bulk actions or inline editing |
| Design system | 85% | Consistent components, light-only palette with WCAG AA asserted by test, loading/empty/error states |
| Testing | 90% | 1,496 tests, 91% backend coverage, query ceilings, concurrency tests |
| CI/CD | 95% | Six gates; docs stale on whether it has run |
| Environments, seeds, migrations, backups | 95% | All verified |

### Overall

**Existing project against its own scope (an LMS): ~93% complete.**

**Existing project against the ERP brief: ~74% complete** (72% at the audit;
phase 12.1 closed the RBAC gap).

The remaining gap is concentrated in seven named items — DSR, soft delete,
export jobs, the manager and counsellor dashboards, the risk/performance engine,
planned-vs-actual course timeline, the counsellor workflow interface, and the UX
speed layer. Every one of them is an **addition**. Nothing in the brief requires
replacing authentication, the database architecture, the API architecture, the
UI component system, or any working feature.

### Progress log

| Phase | Delivered | Backend tests | Frontend tests |
| --- | --- | --- | --- |
| Baseline (6 Sep 2026) | — | 1,339 | 75 |
| 12.1 RBAC / counsellor foundation | Counsellor role, DSR/performance/export capabilities, report-export hardening, capability mirror | 1,415 | 80 |
| 12.2 Reversible deletion | `SoftDeleteModel`, three verbs, recycle bin over every adopting model | 1,444 | 80 |
| 12.3–12.9 Domain features | DSR, course timeline, risk engine, export jobs, transfers and batch kinds | 1,818 | 80 |
| 12.10 Role screens | Manager hubs, counsellor pipeline, trainer end-of-class capture, student dashboard, UX primitives | 1,818 | 581 |

### What is left of the eight gaps

| Gap | State |
| --- | --- |
| DSR | ✅ Closed |
| Soft delete + recovery | ✅ Closed |
| Export jobs | ✅ Closed |
| Manager and counsellor dashboards | ✅ Closed — as two drill-down hubs, per the client |
| Risk / performance engine | ✅ Closed |
| Planned-vs-actual course timeline | ✅ Closed |
| Counsellor workflow interface | ✅ Closed |
| UX speed layer | ✅ Closed |

Two items from the original audit remain open, both known and neither blocking:
**application caching** (Redis runs, the app caches nothing) and **authentication
hardening** (MFA, per-account rate limiting, bounded session revocation).

Three brief items are blocked on a decision rather than on work: inline
"acknowledge a risk flag" and "mark a review done" have no backing state — risk
flags are computed live and reviews carry no status — and "documents" appears in
the brief and nowhere in the API. All three were left unbuilt rather than wired
to endpoints that do not exist.
