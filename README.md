# Grras LMS

A Learning Management System for students, trainers and administrators.

This repository currently contains **Phase 0 (platform foundation)**,
**Phase 1 (identity and people)**, **Phase 2 (courses and learning content)**
and **Phase 3 (batches, enrolment, scheduling and dashboards)**. Attendance,
assignments, exams, certificates and payments are not built yet and are
deliberately absent from the API.

---

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick start (Docker)](#quick-start-docker)
- [Local setup without Docker](#local-setup-without-docker)
- [Environment variables](#environment-variables)
- [Database](#database)
- [Commands](#commands)
- [API](#api)
- [Staging](#staging)
- [Operations](#operations)
- [Release readiness](#release-readiness)
- [Security notes](#security-notes)
- [Deployment overview](#deployment-overview)
- [Troubleshooting](#troubleshooting)

---

## Overview

| Layer | Technology |
| --- | --- |
| Backend API | Python 3.13, Django 5.2 LTS, Django REST Framework, django-filter |
| Database | PostgreSQL 17 |
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind CSS 4, shadcn/ui-style components |
| Infrastructure | Docker, Docker Compose, GitHub Actions |

Requirement-by-requirement completion:
[`docs/phase-0-checklist.md`](docs/phase-0-checklist.md) ·
[`docs/phase-1-checklist.md`](docs/phase-1-checklist.md) ·
[`docs/phase-2-checklist.md`](docs/phase-2-checklist.md) ·
[`docs/phase-3-checklist.md`](docs/phase-3-checklist.md).

**Phase 0 — foundation**

- API-first architecture with a versioned surface (`/api/v1/`) and an OpenAPI schema
- Custom user model with email login and UUID keys
- Append-only audit log usable by every module
- Liveness and readiness health checks with an extensible check registry
- One error envelope for every failure, with request ids for support
- Environment separation with boot-time guards that make cross-environment mistakes impossible
- Automated tests at four levels and CI that gates every pull request

**Phase 1 — identity and people**

- Full authentication: login, logout, sign-out-everywhere, password change,
  password reset and email verification, all rate limited and audited
- Capability-based authorization — one table maps roles to permissions, so a new
  role is one entry rather than an audit of every view
- Student and trainer profile domains with human-readable IDs (`GRS-S-00042`)
- Fee **status** tracking on a student record (a flag, not an accounting system)
- Secure profile image uploads: content verified, re-encoded, EXIF stripped,
  served only to authenticated callers
- Admin interfaces for users, students and trainers with server-side search,
  filtering, sorting and pagination
- Self-service profile, account and security pages for students and trainers

**Phase 2 — courses and learning content**

- Course catalogue with categories, difficulty, objectives and prerequisites
- Modules and lessons with explicit, deterministic ordering and a reorder API
- Four lesson content types — text, video, document, external link — with an
  extension point for more
- Lesson resources: validated file uploads and external links, served only to
  entitled callers
- Video modelled as metadata with a provider abstraction; no video bytes in the
  application container, and playback URLs issued only after an access check
- Draft → review → published → archived workflow with a publishing checklist
- Per-course authoring assignment, so a trainer edits what they were given and
  nothing else
- Student catalogue, course page and a course player with module and lesson
  navigation

**Phase 3 — batches, enrolment and scheduling**

- Batches: cohorts running a course, with a trainer, dates, capacity and a
  five-state lifecycle
- Weekly class schedules with backend conflict detection — a trainer cannot be
  double-booked, and neither can a batch
- Enrolment with capacity enforced under a row lock and a database-level
  one-live-enrolment-per-batch rule
- Course access now gated on a live enrolment; suspending one closes access on
  the next request, and cancelling never destroys history
- One calendar abstraction composed from registered sources
- Student and trainer dashboards, and a minimal progress foundation

---

## Architecture

```
                    browser
                       │  session cookie + CSRF header
                       ▼
┌──────────────────────────────────┐        ┌───────────────────────────────┐
│  frontend  (Next.js, TypeScript) │──────▶ │  backend  (Django + DRF)      │
│  app/ components/ lib/ hooks/    │  JSON  │  config/  apps/  tests/       │
│  no business logic               │        │  services hold business rules │
└──────────────────────────────────┘        └───────────────┬───────────────┘
                                                            │
                                                   ┌────────▼────────┐
                                                   │   PostgreSQL    │
                                                   └─────────────────┘
```

```
backend/
  config/          settings (per environment), URLs, WSGI/ASGI
  apps/
    common/        cross-cutting: errors, pagination, permissions, uploads, logging
    accounts/      identity: user model, roles, capabilities, authentication
    students/      student profile domain
    trainers/      trainer profile domain
    courses/       catalogue, content tree, access rules
    batches/       cohorts, schedules, conflict detection
    enrollments/   participation and progress
    dashboards/    calendar and role dashboards (no models)
    audit/         append-only audit trail
    health/        liveness and readiness probes
  tests/           API and integration tests
frontend/
  app/             routes, layouts, loading/error/404 states
  components/      shell and reusable UI primitives
  lib/             API client, environment access, utilities
  hooks/           data-fetching hooks
  types/           API contract types
  tests/ e2e/      Vitest unit tests and Playwright end-to-end tests
infra/
  docker/          Dockerfiles
  scripts/         entrypoints
docs/              architecture, security, environments
```

Documentation:

| Document | Covers |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | Why the apps are split as they are, the capability model, the service layer |
| [`docs/authentication.md`](docs/authentication.md) | Browser auth, API auth, logout and invalidation, expiry, tokens, enumeration, rate limits |
| [`docs/courses.md`](docs/courses.md) | Content model, ordering, publishing workflow, access rules, video and resource handling |
| [`docs/batches-and-enrolment.md`](docs/batches-and-enrolment.md) | Batches, schedules, conflict detection, enrolment rules, course access, the calendar, query cost |
| [`docs/api.md`](docs/api.md) | Every endpoint, capability matrix, field-level authorization |
| [`docs/security.md`](docs/security.md) | Controls, upload pipeline, threat coverage, what is deliberately not built |
| [`docs/environments.md`](docs/environments.md) | Local, development, staging, production; secrets; seeding |

---

## Requirements

- Docker Engine 24+ with Docker Compose v2 (the only requirement for the Docker path)
- For local non-Docker work: Python 3.13, Node.js 22+, PostgreSQL 17

---

## Quick start (Docker)

```bash
git clone <repository-url> grras-lms
cd grras-lms

cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD (any value locally). The stack refuses to
# start without it, on purpose — no default credential is ever baked in.

docker compose up --build
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:3000 |
| API root | http://localhost:8000/api/ |
| API docs (Swagger UI) | http://localhost:8000/api/docs/ |
| OpenAPI schema | http://localhost:8000/api/schema/ |
| Health (liveness) | http://localhost:8000/health/live/ |
| Health (readiness) | http://localhost:8000/health/ready/ |
| Django admin | http://localhost:8000/admin/ |

Migrations run automatically on backend start (`RUN_MIGRATIONS=true` in
`docker-compose.yml`). Create an administrator:

```bash
docker compose exec backend python manage.py createsuperuser
```

If ports 3000, 8000 or 5432 are already in use, override them in `.env`:
`FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_HOST_PORT`.

Redis is defined but not started by default. Enable it when you need a shared
cache (and later, Celery):

```bash
docker compose --profile redis up
# then set CACHE_URL=redis://redis:6379/0 in .env
```

---

## Local setup without Docker

```bash
# --- Backend
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt

export DJANGO_ENV=local
export DJANGO_SETTINGS_MODULE=config.settings.local
export DATABASE_URL=postgres://grras:yourpassword@localhost:5432/grras_lms

python manage.py migrate
python manage.py runserver

# --- Frontend (second terminal)
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

---

## Environment variables

Every variable is documented in [`.env.example`](.env.example); staging values
in [`.env.staging.example`](.env.staging.example). The most important ones:

| Variable | Purpose |
| --- | --- |
| `DJANGO_ENV` | Declares the environment. Must match the loaded settings module or the process refuses to start. |
| `DJANGO_SETTINGS_MODULE` | `config.settings.{local,development,staging,production,test}` |
| `DJANGO_SECRET_KEY` | Required outside local/test. Must be unique per environment, ≥50 characters. |
| `DJANGO_ALLOWED_HOSTS` | Required in deployed environments. |
| `DATABASE_URL` | PostgreSQL DSN. SQLite is rejected. |
| `CACHE_URL` | Required in deployed environments — rate limiting needs a shared cache. |
| `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` | Exact frontend origins. Wildcards are never used. |
| `NEXT_PUBLIC_API_BASE_URL` | Browser-visible API URL. **Public** — never put a secret in a `NEXT_PUBLIC_*` variable. |
| `FRONTEND_BASE_URL` | Where emailed reset and verification links point. Required in deployed environments. |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP settings. Required in deployed environments — without mail, nobody can reset a password. |
| `DEFAULT_FROM_EMAIL` | Sender address. Required in deployed environments. |
| `DEMO_USER_PASSWORD` | Password for fake staging demo accounts. Never committed. |

**Secrets are never committed.** `.env*` files are git-ignored (only
`*.example` templates are tracked), CI runs gitleaks over the full history, and
deployed environments receive secrets from the platform's secret manager. See
[`docs/security.md`](docs/security.md) and [`docs/environments.md`](docs/environments.md).

---

## Database

PostgreSQL, configured entirely through `DATABASE_URL`.

- `ATOMIC_REQUESTS = True` — each request runs in a transaction and rolls back on error. Health probes and the API discovery route are explicitly exempt so a database blip cannot fail liveness.
- `CONN_MAX_AGE` with `CONN_HEALTH_CHECKS` — connections are reused and validated before use.
- Migrations live with their app. CI fails when a model change has no migration.
- Tests run against real PostgreSQL (never SQLite) so constraints and JSON behaviour are exercised for real.

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py dbshell
```

---

## Commands

`make help` lists everything. The underlying commands:

| Task | Command |
| --- | --- |
| Start / stop | `docker compose up --build` / `docker compose down` |
| Backend tests | `docker compose exec backend pytest --cov` |
| Frontend unit tests | `cd frontend && npm test` |
| End-to-end tests | `cd frontend && npx playwright test` |
| Backend lint | `cd backend && ruff check .` |
| Backend format | `cd backend && ruff format .` |
| Frontend lint | `cd frontend && npm run lint` |
| Frontend types | `cd frontend && npm run typecheck` |
| Frontend build | `cd frontend && npm run build` |
| Security scans | `make security` (bandit, pip-audit, npm audit) |
| Deployment checks | `make check` (`manage.py check --deploy`) |
| Seed fake demo data | `make seed` (requires `DEMO_USER_PASSWORD`) |
| Seed fake course data | `make seed-courses` |
| Seed fake batch data | `make seed-batches` |

---

## API

- **Versioning** — URL path versioning, `/api/v1/...`. A breaking change ships as `/api/v2/`; `v1` keeps working until consumers migrate.
- **Documentation** — OpenAPI 3 at `/api/schema/`, Swagger UI at `/api/docs/` (on in local/development/staging, off in production unless enabled).
- **Errors** — one envelope, always:

  ```json
  {
    "error": {
      "code": "validation_error",
      "message": "The submitted data is invalid.",
      "details": { "email": ["Enter a valid email address."] },
      "request_id": "0f3c1a…"
    }
  }
  ```

- **Pagination** — page-number based, `?page=2&page_size=50`, capped at 100 per page.
- **Authentication** — session cookie (`HttpOnly`, `SameSite=Lax`, `Secure` outside local). Browser clients fetch a CSRF token from `/api/v1/auth/csrf/` and echo it in the `X-CSRFToken` header on unsafe requests.

Endpoint groups (full reference in [`docs/api.md`](docs/api.md)):

| Group | Routes | Access |
| --- | --- | --- |
| Health | `/health/live/`, `/health/ready/` | public |
| Authentication | `/api/v1/auth/…` — csrf, login, logout, logout-all, me, password change/reset, email verification, profile image | mixed; all rate limited where credentials are involved |
| Users | `/api/v1/users/…` — list, create, retrieve, update, activate/deactivate | capability-gated |
| Students | `/api/v1/students/…` — list, create, own profile, retrieve, update, fee status | capability-gated + ownership |
| Trainers | `/api/v1/trainers/…` — list, create, own profile, retrieve, update | capability-gated + ownership |
| Categories | `/api/v1/categories/…` | read: any user · write: `category.manage` |
| Courses | `/api/v1/courses/…` — browse, create, edit, status, thumbnail, authors, modules, reorder | visibility queryset + per-course assignment |
| Modules | `/api/v1/modules/…` — retrieve, edit, status, lessons, reorder | via the parent course |
| Lessons | `/api/v1/lessons/…` — content, edit, status, video playback, resources | content entitlement |
| Resources | `/api/v1/resources/…` — edit, delete, download | content entitlement |
| Batches | `/api/v1/batches/…` — list, create, detail, status, trainer, roster, schedules | visibility queryset + capability |
| Schedules | `/api/v1/schedules/…` — retrieve, edit, delete | via the parent batch |
| Enrolments | `/api/v1/enrollments/…` — list, create, mine, detail, status, progress | scoped per role |
| Progress | `/api/v1/progress/lessons/<id>/completion/` | the enrolled student |
| Calendar | `/api/v1/calendar/` | only the caller's own events |
| Dashboard | `/api/v1/dashboard/student/`, `/api/v1/dashboard/trainer/` | any signed-in user |

Frontend pages: `/login`, `/forgot-password`, `/reset-password`, `/verify-email`,
`/dashboard`, `/profile`, `/settings/account`, `/settings/security`, `/courses`,
`/courses/[slug]`, `/courses/[slug]/learn/[lessonId]`, `/my-batches`,
`/calendar`, `/admin/batches`, `/admin/batches/[batchId]`, `/admin/courses`,
`/admin/courses/[courseId]`, `/admin/categories`, `/admin/users`,
`/admin/students`, `/admin/trainers`, `/status`.

## Staging

Staging mirrors production security with its own database, secrets and storage,
and **fake data only**.

```bash
cp .env.staging.example .env.staging     # then fill in from the secret manager
make staging-up                          # https://localhost:8443
make verify ENV=staging                  # 19 checks; nothing is written

# Seed it — fake data only, and the commands refuse to run in production.
docker compose -f docker-compose.staging.yml --env-file .env.staging \
  exec backend python manage.py seed_demo_data     # then seed_courses,
                                                   # seed_batches, seed_academics
```

Staging is production-shaped rather than production-flavoured: gunicorn,
`DEBUG=False`, the full hardened settings, a Celery worker and scheduler, and
object storage over the S3 protocol. It is served over **https**, because the
hardened settings mark the session cookie `Secure` and a browser on plain http
silently refuses to store it — sign-in appears to work and the next request is
anonymous. Caddy issues the certificate itself, so a browser warns once.

The seed creates 2 administrators, 5 trainers and 20 students — with full,
plainly fake profiles — on the reserved, undeliverable domain
`@demo.grras.invalid`. `seed_courses` then adds 5 categories, 5 courses, 15
modules and 60 lessons of placeholder material, with generated sample files and
video metadata pointing at the reserved `example.invalid` domain. The password comes from `DEMO_USER_PASSWORD`; the command
refuses to run without it, refuses a weak one, and refuses to run at all in
production. Details in [`docs/environments.md`](docs/environments.md).

---

## Operations

Migrations, backups, restores and rollback: [`docs/operations.md`](docs/operations.md).

```bash
make verify ENV=staging      # is this environment actually working?
make migration-check         # fresh install, reverse and re-apply, on a scratch database
make backup ENV=staging      # dump, then prove the dump restores
make secrets                 # secret scan, and prove what it skips is git-ignored
```

Each of these changes nothing it inspects. `verify` seeds nothing and repairs
nothing — a verification script that fixes what it finds cannot tell you whether
the thing was working.

---

## Release readiness

[`docs/RELEASE_READINESS.md`](docs/RELEASE_READINESS.md) is the assessment:
build, tests, security, performance, migrations, backups, staging, known
limitations, and the five tasks that need a person before this can be called
production ready.

It is **not production ready** today, and the report says so in its first line.

---

## Security notes

Full detail in [`docs/security.md`](docs/security.md). In short:

- Authorization is always enforced by the backend. The UI may hide what a user cannot use; that is convenience, never a control.
- Deny by default: every endpoint requires an authenticated, active user unless it explicitly opts out.
- Capability-based permissions in one table, so a new role cannot silently inherit rights.
- Field-level authorization: sending a field you may not change returns 400 naming it, rather than being silently ignored.
- Uploads are content-verified (extension paired with magic bytes), stored under server-generated names, and served only to authenticated, entitled callers.
- Unpublished course content is invisible rather than merely uneditable: a guessed identifier returns 404, because records are resolved inside a queryset the caller is entitled to.
- Course content is gated on a live enrolment, checked on every request, so suspending one closes access immediately.
- Secure headers, secure cookies, HSTS, CSRF protection and CORS with an explicit origin allowlist.
- Rate limiting on authentication endpoints; a shared cache is mandatory in deployed environments so the limit is real.
- Errors never leak internals; unexpected failures return a generic message plus a request id.
- Logs and audit records are scrubbed of passwords, tokens and other secrets before they are written.
- Every login, logout, failed login and administrative action is recorded in an append-only audit log.
- CI runs SAST (bandit), dependency vulnerability scans (pip-audit, npm audit) and secret scanning (gitleaks) on every pull request.

Report a suspected vulnerability privately to the maintainers; do not open a public issue.

---

## Deployment overview

Nothing is deployed to production during Phase 0. When production begins, a
release requires all of: feature testing, security testing, staging validation,
database migration review, backup verification, a rollback plan, passing CI,
production configuration review and release documentation.

The production path is: build the `production` image targets → run
`manage.py migrate` as a separate reviewed step → start gunicorn behind a
TLS-terminating proxy (`NUM_PROXIES` set to the real proxy depth) → serve the
Next.js standalone build → point both at the production secret manager.

---

## Troubleshooting

**`POSTGRES_PASSWORD must be set in .env`** — copy `.env.example` to `.env` and set it. There is no default credential by design.

**Port already in use** — set `FRONTEND_PORT`, `BACKEND_PORT` or `POSTGRES_HOST_PORT` in `.env`.

**`Environment mismatch: DJANGO_ENV=... but config.settings.X was loaded`** — this guard is doing its job. Make `DJANGO_ENV` and `DJANGO_SETTINGS_MODULE` refer to the same environment.

**`DJANGO_SECRET_KEY must be at least 50 characters`** — generate one: `python -c "import secrets;print(secrets.token_urlsafe(64))"`.

**Frontend cannot reach the API / CORS errors** — `NEXT_PUBLIC_API_BASE_URL` must be the URL the *browser* can reach, and that exact origin must appear in `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`.

**403 `csrf_failed` on a POST** — fetch `/api/v1/auth/csrf/` first and send the cookie value back in the `X-CSRFToken` header. The bundled API client does this automatically.

**Backend restarts before the database is ready** — the entrypoint waits up to `DB_WAIT_TIMEOUT` seconds (default 60). Check `docker compose logs db`.

**Database changes not applied** — `docker compose exec backend python manage.py migrate`. To start completely fresh: `docker compose down -v` (this destroys local data).
# lmsSchool
