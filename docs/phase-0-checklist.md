# Phase 0 — completion checklist

**Status: complete.** Every Phase 0 requirement is implemented and verified.
Items marked *Deferred* were explicitly out of scope for this phase and are
recorded here so nobody assumes a control or feature exists that does not.

Last verified: 2026-08-31 · 133 tracked files · 111 automated tests passing

| Symbol | Meaning |
| --- | --- |
| ✅ | Done and verified by a test, a scan or a live run |
| 🟡 | Foundation in place, full feature intentionally deferred to a later phase |
| ⬜ | Deferred — not part of Phase 0 |

---

## Summary

| Area | Status |
| --- | --- |
| Repository structure | ✅ |
| Django backend runs | ✅ |
| Next.js frontend runs | ✅ |
| PostgreSQL runs | ✅ |
| Docker environment | ✅ |
| Backend ↔ PostgreSQL | ✅ |
| API foundation | ✅ |
| Frontend ↔ API | ✅ |
| Custom user model | ✅ |
| Permission architecture | ✅ |
| Audit logging foundation | ✅ |
| Health checks | ✅ |
| Automated tests | ✅ |
| CI | ✅ (authored; never executed on GitHub — no remote yet) |
| Security checks | ✅ |
| Secret scanning | ✅ |
| Staging configuration | ✅ (built and run locally) |
| Fake staging seed data | ✅ |
| Documentation | ✅ |
| No secrets committed | ✅ |
| Production config separated | ✅ |

---

## §2 Technology

| Requirement | Status | Where |
| --- | --- | --- |
| Python | ✅ 3.13 | `infra/docker/backend.Dockerfile` |
| Django 5.2 LTS | ✅ 5.2.17 | `backend/requirements/base.txt` |
| Django REST Framework | ✅ 3.18.0 | same |
| PostgreSQL | ✅ 17 | `docker-compose.yml` |
| Next.js | ✅ 16.3.3 | `frontend/package.json` |
| TypeScript | ✅ 5.9.3, strict | `frontend/tsconfig.json` |
| Tailwind CSS | ✅ 4.3.3 | `frontend/app/globals.css` |
| shadcn/ui | ✅ source-owned primitives | `frontend/components/ui/` |
| Docker + Compose | ✅ | `infra/docker/`, `docker-compose*.yml` |
| Git | ✅ initialised | (no commits made — left to the team) |
| CI/CD | ✅ CI authored | `.github/workflows/ci.yml` |
| Only necessary, maintained dependencies | ✅ | 6 backend runtime packages, 8 frontend runtime packages, all pinned |

---

## §3 Architecture

| Requirement | Status | Notes |
| --- | --- | --- |
| Frontend / API / DB / infra separated | ✅ | No shared code, no direct DB access from the frontend |
| API-first | ✅ | Frontend talks only over documented HTTP |
| Frontend communicates via documented API | ✅ | OpenAPI schema at `/api/schema/` |
| No business logic in React components | ✅ | Transport in `lib/`, async state in `hooks/` |
| No business logic in serializers | ✅ | Rules live in `apps/<app>/services.py` |
| Domain-based Django apps | ✅ | `common`, `accounts`, `audit`, `health` |
| Structure deviations documented | ✅ | `docs/architecture.md` §2 explains why `audit` and `health` are separate apps |

---

## §4 Environment separation

| Requirement | Status | Notes |
| --- | --- | --- |
| Local / Development / Staging / Production | ✅ | Plus `test` for pytest |
| Dev config cannot reach production | ✅ | `require_environment()` aborts boot on `DJANGO_ENV` mismatch |
| `.env.example` | ✅ | Plus `.env.staging.example`, `frontend/.env.example` |
| Environment-specific config patterns | ✅ | `base` → `hardened` → per-environment modules |
| No secrets committed | ✅ | gitleaks clean; only `*.example` tracked |
| `.gitignore` entries | ✅ | `.env*`, keys, certs, credentials, build output |
| Secret supply documented | ✅ | `docs/environments.md`, `docs/security.md` §1 |

---

## §5 Docker

| Requirement | Status | Notes |
| --- | --- | --- |
| Django, PostgreSQL, Next.js | ✅ | All three in `docker-compose.yml` |
| Redis/Celery addable without redesign | ✅ | `redis` service behind `--profile redis`; `CACHE_URL` env already wired |
| Documented start command | ✅ | `docker compose up --build` |
| Setup + troubleshooting documented | ✅ | README "Quick start" and "Troubleshooting" |
| Non-root containers | ✅ | Both images |
| Healthchecks | ✅ | db, backend, frontend |

---

## §6 Django configuration

| Requirement | Status |
| --- | --- |
| Separate config per environment | ✅ |
| `DEBUG=False` in deployed environments | ✅ hard-coded, not an env var |
| `ALLOWED_HOSTS` | ✅ required, no default |
| CSRF configuration | ✅ trusted origins required |
| CORS configuration | ✅ explicit allowlist, credentials on, no wildcard |
| Secure cookies | ✅ HttpOnly + SameSite + Secure |
| HSTS | ✅ 1 year + subdomains + preload (production) |
| Secure proxy handling | ✅ trusted only when `NUM_PROXIES > 0` |
| Security headers | ✅ CSP, Permissions-Policy, nosniff, referrer, COOP, frame-deny |
| Trusted origins | ✅ |
| Static files | ✅ WhiteNoise, hashed manifest |
| Media files | ✅ outside web root, restrictive permissions |
| Logging | ✅ JSON in deployment, request id on every line, secrets redacted |
| Error reporting | ✅ Sentry, opt-in via DSN, `send_default_pii=False` |
| No global weakening for dev | ✅ relaxations only in `local.py` |
| `check --deploy` passes | ✅ 0 issues, `--fail-level WARNING`, production and staging |

---

## §7 Database

| Requirement | Status | Notes |
| --- | --- | --- |
| PostgreSQL | ✅ | |
| Connection via environment | ✅ | single `DATABASE_URL` |
| SQLite rejected | ✅ | `forbid_sqlite()` guard |
| Connection settings | ✅ | `CONN_MAX_AGE`, `CONN_HEALTH_CHECKS`, optional `sslmode` |
| Migrations | ✅ | 2 initial migrations; CI checks for drift |
| Health checks | ✅ | database probe in readiness |
| Transaction-safe patterns | ✅ | `ATOMIC_REQUESTS=True`; probes exempt; services use `@transaction.atomic` |
| Minimum models only | ✅ | `User` + `AuditLog`. No LMS schema |

---

## §8 API

| Requirement | Status | Notes |
| --- | --- | --- |
| DRF set up | ✅ | |
| Versioning strategy | ✅ | URL path `/api/v1/`, explicit `ALLOWED_VERSIONS` |
| Error response format | ✅ | one envelope: `code`, `message`, `details`, `request_id` |
| Pagination strategy | ✅ | page-number, `page_size` capped at 100 |
| Validation approach | ✅ | `StrictSerializer` rejects unknown fields; model + DB backstops |
| Authentication foundation | ✅ | session auth, CSRF, rate limited |
| Permission foundation | ✅ | deny-by-default + role classes |
| API documentation | ✅ | `docs/api.md` + Swagger UI |
| OpenAPI/Swagger prepared | ✅ | drf-spectacular, `/api/schema/`, `/api/docs/` |
| Consistent responses | ✅ | tested in `tests/test_errors.py` |
| No unimplemented future endpoints | ✅ | 8 routes, all implemented |

---

## §9 Frontend

| Requirement | Status | Where |
| --- | --- | --- |
| Next.js application | ✅ | App Router |
| Clean base UI | ✅ | token-driven design system |
| Application layout | ✅ | `components/app-shell.tsx` |
| Navigation shell | ✅ | same, with skip link and landmarks |
| Loading state | ✅ | `components/states.tsx`, `app/loading.tsx` |
| Error state | ✅ | `components/states.tsx`, `app/error.tsx` |
| Empty state | ✅ | `components/states.tsx` |
| 404 page | ✅ | `app/not-found.tsx` |
| Responsive behaviour | ✅ | fluid layout, responsive grid |
| Reusable component system | ✅ | `components/ui/`: button, card, alert, badge, skeleton |
| No LMS dashboards | ✅ | only overview + system status |

---

## §10 Authentication foundation

| Requirement | Status | Notes |
| --- | --- | --- |
| Custom user model before migrations | ✅ | created in the initial migration |
| No temporary user model | ✅ | `accounts.User` is final |
| Role handling prepared | ✅ | `UserRole` on the user record, authoritative |
| Permission handling prepared | ✅ | `apps/common/permissions.py` |
| Session/token strategy prepared | ✅ | sessions implemented; token path documented, not built |
| Audit logging prepared | ✅ | `apps/audit` |
| Minimal login to validate foundation | ✅ | csrf / login / logout / me + admin user list |
| Full login system | 🟡 | no password reset, no MFA, no lockout — Phase 1 |
| Frontend login UI | ⬜ | Phase 1 |

---

## §11 Security baseline

| Control | Status | Notes |
| --- | --- | --- |
| Input validation | ✅ | serializers + validators + DB constraints |
| Output encoding | ✅ | JSON-only API, React escaping, no `dangerouslySetInnerHTML` |
| Secure authentication foundation | ✅ | hashed passwords, 12-char policy, session cycling, generic failures |
| Authorization foundation | ✅ | deny-by-default, server-side role checks |
| CSRF protection | ✅ | incl. anonymous POST gap closed by `EnforceCSRFMixin` |
| Secure cookies | ✅ | verified live on the staging stack |
| Rate limiting architecture | ✅ | named scopes, env-configurable, shared cache mandatory |
| Secure HTTP headers | ✅ | backend and frontend independently |
| Errors without sensitive info | ✅ | generic 500 + request id; tested |
| Secret management | ✅ | no defaults, no commits, per-environment |
| Dependency security | ✅ | pip-audit, npm audit, Dependabot |
| Security logging | ✅ | `grras.security` channel, redaction filter |
| Audit logging foundation | ✅ | `apps/audit` |
| Safe file handling architecture | ✅ | size limits, outside web root, `0o640` |
| No secrets in source control | ✅ | gitleaks clean |
| Backend enforces all authorization | ✅ | tested per role |

---

## §12 Audit logging foundation

| Field / property | Status |
| --- | --- |
| Actor (+ label surviving deletion) | ✅ |
| Action | ✅ stable `TextChoices` |
| Resource | ✅ |
| Resource ID | ✅ |
| Timestamp | ✅ indexed |
| Result | ✅ success / failure / denied |
| Request metadata | ✅ IP, user agent, request id, method, path |
| No passwords, tokens or secrets stored | ✅ scrubbed at the single write point |
| Reusable by future modules | ✅ one function: `apps.audit.services.record()` |
| Append-only | ✅ save/delete raise; admin read-only |

---

## §13 Health checks

| Requirement | Status |
| --- | --- |
| Application endpoint | ✅ `/health/live/` — no DB dependency |
| Database endpoint | ✅ `/health/ready/` — 503 when degraded |
| Ready for Redis | ✅ cache probe already registered |
| Ready for worker | 🟡 add a function to `READINESS_CHECKS` |
| Ready for storage | 🟡 same |
| No secrets or config exposed | ✅ tested |

---

## §14 Automated tests

| Requirement | Status | Count |
| --- | --- | --- |
| Backend unit framework | ✅ pytest + pytest-django | |
| API test framework | ✅ DRF test client | |
| Frontend test framework | ✅ Vitest + Testing Library | |
| End-to-end framework | ✅ Playwright | |
| Test database strategy | ✅ real PostgreSQL, per-test transaction rollback | |
| **Backend total** | ✅ | **89 passed**, 85% coverage |
| **Frontend unit total** | ✅ | **17 passed** |
| **End-to-end total** | ✅ | **5 passed** |

Required smoke proofs:

| Proof | Status |
| --- | --- |
| 1. Backend starts | ✅ |
| 2. Database connects | ✅ |
| 3. API responds | ✅ |
| 4. Frontend starts | ✅ |
| 5. Frontend communicates with backend | ✅ live `/status` page, E2E-verified |
| 6. Health endpoint works | ✅ incl. the degraded path |

---

## §15 CI

| Check | Status | Job |
| --- | --- | --- |
| Backend formatting | ✅ | `backend` (ruff format --check) |
| Backend linting | ✅ | `backend` (ruff check) |
| Backend tests | ✅ | `backend` (pytest + coverage, PostgreSQL service) |
| Frontend linting | ✅ | `frontend` (eslint) |
| Frontend type checking | ✅ | `frontend` (tsc --noEmit) |
| Frontend tests | ✅ | `frontend` (vitest) |
| Build validation | ✅ | `frontend` (next build) + `docker-build` (both production images) |
| Dependency/security checks | ✅ | `backend-security` (bandit, pip-audit), `frontend` (npm audit) |
| Secret scanning | ✅ | `secret-scan` (gitleaks, full history) |
| PR fails on critical failure | ✅ | `ci-passed` aggregate job for branch protection |
| Extras | ✅ | migration drift check, `check --deploy`, end-to-end job on the compose stack |
| **Executed on GitHub** | ⬜ | no remote yet — every command was run locally instead |

---

## §16 Staging

| Requirement | Status | Notes |
| --- | --- | --- |
| Separate database | ✅ | own service, own volume, own role |
| Separate secrets | ✅ | `.env.staging` / secret manager, never production values |
| Separate storage | ✅ | `staging_media` volume |
| `DEBUG=False` | ✅ | verified on the running stack |
| Production-like security | ✅ | same `hardened.py` baseline as production |
| Fake seed data only | ✅ | `@demo.grras.invalid` (RFC 2606 reserved) |
| Never production credentials | ✅ | enforced by the environment guard |
| Never real student data | ✅ | no import path exists |
| Seed mechanism | ✅ | `manage.py seed_demo_data` |
| 1 admin / 2 trainers / 10 students | ✅ | verified live |
| Clearly fake information | ✅ | placeholder names, undeliverable domain |
| Credentials documented safely | ✅ | account list in `docs/environments.md`; password only in the secret manager |
| No real passwords in Git | ✅ | command refuses to run without `DEMO_USER_PASSWORD` |

---

## §17 Documentation

| Document | Status |
| --- | --- |
| `README.md` — overview, architecture, requirements, local + Docker setup, env vars, DB, test/lint/build commands, staging, security, deployment, troubleshooting | ✅ |
| `docs/architecture.md` | ✅ |
| `docs/security.md` | ✅ |
| `docs/environments.md` | ✅ |
| `docs/api.md` (additional) | ✅ |
| `docs/phase-0-checklist.md` (this file) | ✅ |

---

## §18 Production-readiness rules

Applied to everything shipped in this phase.

| Rule | Status |
| --- | --- |
| Code works | ✅ run live, not only compiled |
| Tests exist | ✅ 111 |
| Tests pass | ✅ |
| API documented | ✅ |
| Permissions enforced server-side | ✅ tested per role |
| Validation exists | ✅ |
| Errors handled safely | ✅ |
| Security implications reviewed | ✅ 5 defects found and fixed (see below) |
| Logs expose no secrets | ✅ redaction filter + tests |
| Configuration environment-specific | ✅ |
| Staging reproduces the feature | ✅ stack built and run |
| Documentation updated | ✅ |

### Defects found during verification and fixed

| # | Defect | Fix |
| --- | --- | --- |
| 1 | DRF marks API views `csrf_exempt`, so anonymous POST (login) had no CSRF check → login CSRF | `apps/common/mixins.py::EnforceCSRFMixin` |
| 2 | `ATOMIC_REQUESTS` made liveness depend on the database → a DB blip would kill healthy instances | probes marked `non_atomic_requests` |
| 3 | `redis` client not declared although `CACHE_URL` is mandatory in deployed environments → staging readiness 503 | added to `requirements/prod.txt` + regression test |
| 4 | Every 401/403 was reported to clients as `"The submitted data is invalid."` | `_normalise_detail()` fixed + regression tests |
| 5 | `SECURE_PROXY_SSL_HEADER` trusted unconditionally → a directly reachable app would believe a client-supplied `X-Forwarded-Proto` | set only in `hardened.py`, only when `NUM_PROXIES > 0` |

---

## §19 Release rule

| Requirement | Status |
| --- | --- |
| Nothing deployed to production in this phase | ✅ |
| Feature testing | ✅ |
| Security testing | ✅ |
| Staging validation | ✅ |
| Database migration review | 🟡 two initial migrations, reviewed; no production migration path exercised |
| Backup verification | ⬜ no backup procedure exists yet |
| Rollback plan | ⬜ not written yet |
| CI passing | 🟡 all checks pass locally; never run on GitHub |
| Production configuration review | 🟡 `check --deploy` clean; real values not yet provisioned |
| Release documentation | ⬜ Phase 1 |

---

## §21 Mandatory workflow

| Step | Status |
| --- | --- |
| 1. Inspect existing repository | ✅ empty directory |
| 2. Do not overwrite existing work | ✅ nothing to overwrite |
| 3. Identify existing architecture | ✅ none |
| 4. Identify conflicts | ✅ none |
| 5. Implementation plan | ✅ |
| 6. Implement Phase 0 | ✅ |
| 7. Run tests | ✅ 111 passing |
| 8. Run linting | ✅ ruff, eslint |
| 9. Run type checks | ✅ tsc |
| 10. Run security checks | ✅ bandit, gitleaks, `check --deploy` |
| 11. Run dependency checks | ✅ pip-audit, npm audit |
| 12. Run the application | ✅ local and staging stacks |
| 13. Verify database connectivity | ✅ |
| 14. Verify frontend/backend communication | ✅ |
| 15. Verify staging configuration | ✅ built and run |
| 16. Create seed data | ✅ |
| 17. Test the seed data | ✅ incl. refusal paths |
| 18. Update documentation | ✅ |
| 19. Review the code for security issues | ✅ 5 defects fixed |
| 20. Final implementation report | ✅ |

---

## Outstanding — requires a human

Not blockers for Phase 0, but required before anything is deployed:

1. Provision real secret-manager entries per environment (`DJANGO_SECRET_KEY`, `DATABASE_URL`, `CACHE_URL`, `DEMO_USER_PASSWORD`).
2. Decide the domain layout. The frontend and API must share a registrable domain — `SameSite=Lax` session cookies depend on it.
3. Push to a remote and enable branch protection requiring the `CI passed` check; confirm the first Actions run is green.
4. Provision staging infrastructure: separate database server, Redis, storage volume, TLS ingress, and the correct `NUM_PROXIES`.
5. Write backup and rollback procedures — neither exists.
6. Decide whether to enable Sentry (`SENTRY_DSN` currently unset, so it is off).

---

## Next phase

Phase 1 builds the first real domain slice on these patterns:

- Login UI, password reset and email verification
- Courses → Modules → Lessons (`BaseModel`, rules in `services.py`, routes in `config/api_urls.py`, audited writes)
- Batches and Enrollments using `IsSelfOrAdmin` for ownership
- Redis promoted from a compose profile to a declared dependency
- TypeScript types generated from the OpenAPI schema so the contract cannot drift
