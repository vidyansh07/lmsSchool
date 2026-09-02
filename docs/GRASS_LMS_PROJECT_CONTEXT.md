# Grass LMS — project context

The single orientation document. Written from the actual repository, not from a
plan. If this disagrees with the code, the code is right and this file is stale —
fix it.

---

## What this is

A Learning Management System for Grass Solutions. **An LMS, not an ERP.**

In scope: people, courses, content, batches, enrolment, sessions, attendance,
assignments, assessments, projects, exams, results, progress, completion,
certificates, notifications, calendar, reports, analytics, LMS administration.

Explicitly out of scope unless separately requested: payments, accounting,
payroll, HR, CRM, sales, procurement, inventory, placement ERP.

One deliberate exception already shipped: `StudentProfile.fee_status` is a
*status flag* (pending / partial / paid / waived / overdue). It carries no
amounts, no transactions and no gateway — see `docs/DECISIONS.md` D-011.

---

## Stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.13, Django 5.2 LTS, Django REST Framework, django-filter |
| Database | PostgreSQL 17 |
| Frontend | Next.js 16 (App Router), TypeScript strict, Tailwind 4, shadcn/ui-style owned components |
| Infrastructure | Docker Compose; Redis defined behind a profile; S3 not yet wired |
| Testing | pytest + pytest-django, Vitest + Testing Library, Playwright |
| CI | GitHub Actions — format, lint, types, tests, build, SAST, dependency audit, secret scan, E2E |

Django stays on the current 5.2 patch line. No major framework upgrade during
feature work.

---

## Architecture in one page

```
frontend (Next.js)            backend (Django + DRF)          PostgreSQL
  app/ components/     ──►      config/  apps/          ──►
  lib/  hooks/  types/          services hold the rules
  no business logic             views only shape HTTP
```

**Apps and what each owns**

| App | Owns |
| --- | --- |
| `common` | Errors, pagination, permissions, uploads, logging, middleware, identifiers |
| `accounts` | User, roles, the capability matrix, authentication flows |
| `students` / `trainers` | Domain profiles |
| `courses` | Category, Course, Module, Lesson, Resource, VideoAsset, authoring assignment, content access |
| `batches` | Batch, BatchSchedule, conflict detection, batch/enrolment access |
| `enrollments` | Enrollment, LessonProgress |
| `sessions` | ClassSession (app label `class_sessions`), trainer assignment history |
| `attendance` | AttendanceRecord, the register, corrections, attendance percentages |
| `assignments` | Assignment, AssignmentSubmission, SubmissionFile, grading |
| `assessments` | Assessment (weekly tests), AssessmentResult, ResultImport |
| `academics` | AcademicPolicy — the configurable rules, and how they resolve |
| `projects` | Project, StudentProject (the review loop), ProjectFile |
| `questions` | The question bank: Question, QuestionOption. Holds the answers |
| `exams` | Exam, ExamSection, ExamAttempt, AttemptQuestion, AttemptAnswer |
| `progress` | The one progress calculation, the completion rules, CourseCompletion |
| `certificates` | CertificateTemplate, Certificate, PDF and QR, public verification |
| `notifications` | Notification, preferences, the email outbox and channel registry |
| `announcements` | Announcement, audience rules, fan-out on publish |
| `discussions` | Thread, Reply, moderation |
| `learning` | Bookmarks, lesson notes, continue-learning, the batch directory |
| `reporting` | The ten reports, nine metrics with definitions, dashboards, CSV export, bulk import |

Phase 9 added no app. It added three modules that cut across them:
`apps/common/storage.py` (private object storage), `apps/common/scanning.py`
(the malware-scan seam), and `apps/progress/bulk.py` (the cohort-sized gathering
behind the one progress calculation). Plus `config/celery.py`, the worker.

Phase 10 added no application code beyond closing gaps the release journey
found. What it added is around the edges: a production-shaped staging stack
(`docker-compose.staging.yml`, `infra/proxy/`), the operational scripts
(`scripts/verify_demo.sh`, `scripts/backup.sh`, `scripts/check_migrations.sh`),
and `frontend/middleware.ts`, which owns the Content-Security-Policy because it
needs a per-request nonce. Start at `docs/RELEASE_READINESS.md`.
| `dashboards` | No models — the calendar registry and role dashboards |
| `audit` | Append-only audit trail |
| `health` | Liveness and readiness probes |

**Five rules that hold everywhere.** Break one and the review fails.

1. **Business rules live in `services.py`.** Not in serializers, not in views. A
   rule in a serializer only holds for requests that use that serializer.
2. **Authorization is a queryset first, a check second.** Records are resolved
   inside a queryset the caller is already entitled to, so a guessed id 404s
   before any permission code runs. `<resource>_id` from a client is never proof
   of anything.
3. **Serializers are scoped by caller, and reject unknown fields.** A student and
   an administrator editing the same record use different classes. Sending a
   field you may not set returns 400 naming it.
4. **Capabilities, not role checks.** `apps/accounts/roles.py` maps role →
   capabilities. Views declare what they need. A new role is one table entry.
5. **Every state change is audited**, and failures are audited *durably* —
   outside the request transaction, so a rollback cannot erase the record of it.

---

## Roles

`SUPERADMIN`, `ADMIN`, `MANAGER`, `TRAINER`, `STUDENT`.

Scoping that is not expressible as a global capability is resolved per record:

* a trainer edits the courses they are **assigned** to (`CourseAssignment`);
* a trainer sees the batches they are **assigned** to teach (`Batch.trainer`);
* a student sees their **own** enrolments and nothing else.

Only authorised administrators enrol students. Students never self-enrol.

---

## Authentication

Django session cookies — `HttpOnly`, `SameSite=Lax`, `Secure` outside local —
with CSRF enforced, including on anonymous POSTs where DRF would otherwise skip
it. No JWT. Full detail in `docs/authentication.md`.

---

## Course access

A student reaches non-preview lesson content, resources or video only when: the
account is active, an enrolment is `active` or `completed`, the batch is not
cancelled, and today falls inside any access window.
`Enrollment.grants_access()` is the single definition; it is consulted live, so
suspending an enrolment closes access on the next request.

---

## Environments

`local` · `development` · `staging` · `production` · `test`. Each asserts its own
identity at boot: a `DJANGO_ENV` that disagrees with the loaded settings module
refuses to start. Deployed environments have **no defaults** for secrets, hosts,
database, cache, mail or the frontend URL.

Only fake data ever exists outside production: `@demo.grras.invalid` and
`example.invalid` are RFC 2606 reserved and undeliverable by construction.

---

## Where to look

| Question | File |
| --- | --- |
| What is built, and is it really done? | `docs/FEATURE_STATUS.md` |
| Why is it like this? | `docs/DECISIONS.md` |
| How do the pieces fit? | `docs/architecture.md` |
| What are the security controls? | `docs/security.md` |
| How does login work? | `docs/authentication.md` |
| What endpoints exist? | `docs/api.md` |
| Course content model | `docs/courses.md` |
| Batches, enrolment, calendar | `docs/batches-and-enrolment.md` |
| Environments and secrets | `docs/environments.md` |
| Is it releasable? | `docs/RELEASE_READINESS.md` |

Per-phase requirement traceability lives in `docs/phase-N-checklist.md`.
