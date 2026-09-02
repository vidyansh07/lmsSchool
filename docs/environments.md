# Environments

Four environments, plus a test configuration used by the automated suites.
They are isolated by construction: separate databases, separate secrets,
separate storage, and a boot-time guard that makes cross-wiring fail loudly.

| Environment | Settings module | `DJANGO_ENV` | DEBUG | Data | Purpose |
| --- | --- | --- | --- | --- | --- |
| Local | `config.settings.local` | `local` | on | throwaway | Developer machine / docker compose |
| Development | `config.settings.development` | `development` | **off** | fake | Shared deployed dev server |
| Staging | `config.settings.staging` | `staging` | **off** | fake only | Pre-production validation gate |
| Production | `config.settings.production` | `production` | **off** | real | Live service |
| Test | `config.settings.test` | `test` | off | ephemeral | pytest / CI |

---

## How environments are kept apart

**1. The environment is asserted at boot.** Every settings module calls
`require_environment("<name>")`, comparing against `DJANGO_ENV` from the
runtime. A mismatch stops the process:

```
ImproperlyConfigured: Environment mismatch: DJANGO_ENV='production' but
config.settings.local was loaded. Refusing to start so that one environment
cannot accidentally use another's configuration.
```

This is what prevents a development configuration from ever pointing at a
production database: the credentials come from `DATABASE_URL` in the same
environment block as `DJANGO_ENV`, so using production credentials requires
declaring `DJANGO_ENV=production`, which then refuses to load development
settings.

**2. Deployed environments have no defaults.** `DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`,
`DATABASE_URL`, `CACHE_URL`, `EMAIL_HOST`, `DEFAULT_FROM_EMAIL` and
`FRONTEND_BASE_URL` must all be supplied. A missing value raises
`ImproperlyConfigured` rather than falling back to something permissive.

Mail is in that list because an environment that cannot send email cannot reset
a password — a silent console fallback would look fine until a locked-out user
needed it.

**3. Secure defaults live in `base.py`.** Development relaxations exist only in
`local.py`. A forgotten override fails towards "too strict".

**4. SQLite is rejected** outside the test environment.

**5. Demo seeding is gated** on `ALLOW_DEMO_SEED`, which is `False` in
production.

---

## Secrets

| Environment | Where secrets come from |
| --- | --- |
| Local | `.env`, git-ignored, created from `.env.example` |
| Development / Staging / Production | The deployment platform's secret manager, injected as process environment variables |

Rules:

- Never commit a secret. Only `*.example` templates are tracked.
- Never reuse a secret across environments.
- Rotate `DJANGO_SECRET_KEY` per environment; rotating it invalidates existing
  sessions, which is the intended behaviour after a suspected exposure.
- `NEXT_PUBLIC_*` values are inlined into the browser bundle and are **public**
  by definition. Never put a secret in one.

---

## Local

```bash
cp .env.example .env      # set POSTGRES_PASSWORD
docker compose up --build
```

Frontend on :3000, API on :8000, PostgreSQL on :5432 (override with
`FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_HOST_PORT`).

Relaxations, scoped to `local.py` only: `DEBUG=True`, non-Secure cookies (plain
HTTP), no SSL redirect, no HSTS, permissive `ALLOWED_HOSTS`, API docs enabled,
email printed to the console.

---

## Development (deployed)

A shared, network-reachable dev server. It uses the hardened baseline —
`DEBUG=False`, Secure cookies, SSL redirect, HSTS — with verbose logging and
API docs enabled. It gets its own database and secrets, and holds fake data.

---

## Staging

Staging is production with a different blast radius. It exists to answer one
question before a release: *does this work with production-shaped
configuration?*

Requirements, all enforced or documented:

- Separate database (own server, or at minimum own database **and** role)
- Separate secrets — never a production value
- Separate storage volume
- `DEBUG=False`
- Production-like security configuration
- **Fake seed data only. Never production credentials. Never real student data.**

```bash
cp .env.staging.example .env.staging     # fill in from the secret manager
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
docker compose -f docker-compose.staging.yml exec backend python manage.py seed_demo_data
```

The staging stack uses the production image targets (gunicorn, Next.js
standalone), its own Redis, and its own named volumes.

### Seed data

`python manage.py seed_demo_data` creates:

| Count | Role | Email pattern |
| --- | --- | --- |
| 2 | admin | `admin@…`, `admin2@…` |
| 5 | trainer | `trainer1@…` … `trainer5@…` |
| 20 | student | `student1@…` … `student20@…` |

Students and trainers get complete, plainly fake profiles: addresses in
Rajasthan, placeholder institutions, varied fee statuses, and trainer skill sets
across Linux, Python, cloud, networking and data science. Demo accounts are
created pre-verified, since a `.invalid` address can never receive a
verification email.

Safety properties:

1. **Refuses to run in production** (`ALLOW_DEMO_SEED` is `False` there).
2. **No password in source control.** The password comes from
   `DEMO_USER_PASSWORD`; without it the command exits with an error rather than
   inventing a guessable default, and it also refuses a password that fails the
   project's password policy.
3. **Obviously fake data.** `.invalid` is reserved by RFC 2606 and can never be
   delivered to a real inbox; all names are placeholders.
4. **Idempotent.** Re-running updates the demo accounts *and their profiles*
   and never touches non-demo ones; no duplicate users or profiles are created.
   `--force` also resets their passwords.

### Where the staging credentials are documented

The account list is above; it is not secret. The password is **not** written
anywhere in this repository. It lives in the staging secret manager entry
`DEMO_USER_PASSWORD`, and reviewers read it from there (or from a local,
untracked `.env.staging`). Rotate it by changing that entry and re-running the
seed with `--force`.

---

## Production

Strictest configuration, fails closed. `DEBUG` is hard-coded `False`. API docs
are off unless explicitly enabled. HSTS is one year with subdomains and
preload. A shared cache is mandatory. Static files are served by WhiteNoise
with hashed, compressed manifests.

**Nothing is deployed to production during Phase 0.** A production release
requires all of: feature testing, security testing, staging validation,
database migration review, backup verification, a rollback plan, passing CI,
production configuration review and release documentation.

### Deployment requirement: same registrable domain

Session cookies are `SameSite=Lax`. The frontend and API must therefore share a
registrable domain — for example `app.grras.example` and `api.grras.example`,
or one domain with the API under a path. Hosting them on unrelated domains
would require `SameSite=None`, weakening CSRF defence in depth.

---

## Adding a new environment

1. Create `config/settings/<name>.py`; import from `hardened.py` and call
   `require_environment("<name>")`.
2. Add `<name>` to `ENVIRONMENTS` in `config/settings/guards.py`.
3. Create the secret manager entries — never copy another environment's.
4. Provision its own database, cache and storage.
5. Add an `.env.<name>.example` template documenting every variable.
6. Extend CI if the environment needs its own deployment checks.
