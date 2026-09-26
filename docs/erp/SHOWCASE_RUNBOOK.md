# The showcase data set, and what production needs

Two audiences, one document. The first half is for whoever shows the product:
how to fill an environment with data that exercises every screen, who to sign
in as, and what each screen is then meant to show. The second half is for
whoever promotes it: exactly which environment values must change, which must
not be set, and what the showcase deliberately cannot do there.

---

## 1. What the showcase is

`manage.py seed_showcase` layers a coherent, connected data set on top of
whatever the database already holds. It is **additive**: it deletes nothing. On
staging it runs alongside the existing demo accounts (`@demo.grras.invalid`)
and the imported SITP records, and it attaches the missing halves of those
records — fee plans, risk, activities, published course content — rather than
replacing them.

The point is coverage. Before it, most screens were empty because the database
had, for example, two fee plans and no activities at all: the fee ledger, the
ageing chart, the counsellor's queue and the recovery bin had nothing to draw.
A screen that is empty because the data is thin looks identical to a screen
that is broken, which is why "some pages are not opening" was the symptom.

Four properties it keeps:

| Property | What it means |
|---|---|
| Additive | Nothing is deleted. Four rows are *overwritten* every run — institution settings, branding, the global academic policy and five policy keys — and `apps/common/showcase/__init__.py` says so. |
| Idempotent | Run it twice and the second run creates nothing. The summary's `created` column reads 0. |
| Gated | Refuses unless `ALLOW_DEMO_SEED` is true (local, development, test, staging). Production refuses before touching anything. |
| No password on disk | Every account shares the value of `DEMO_USER_PASSWORD`. It is validated against the project's password policy, kept out of logs, tracebacks and `repr()`, and printed nowhere. |

It also refuses to run when `EMAIL_BACKEND` could deliver mail, because the
stages fan notifications out to every account they concern and a staging
database holds imported real addresses. Only the four Django backends that
deliver nowhere are accepted (`console`, `locmem`, `dummy`, `filebased`);
`--allow-real-mail` is the deliberate way past that. The finish stage then
abandons the outbox rows the run queued, because a Celery worker sends under
*its* mail backend later, not the command's.

---

## 2. Running it

```bash
# local
make seed-showcase                       # needs DEMO_USER_PASSWORD in .env

# staging, from a laptop with the deploy key
./scripts/deploy.sh ubuntu@<host> --key vidyansh.pem --branch main --showcase

# on the host, or anywhere
python manage.py seed_showcase --list            # the ten stages
python manage.py seed_showcase --dry-run         # what would run
python manage.py seed_showcase --only fees       # one stage, on a seeded database
python manage.py seed_showcase --from work        # that stage to the end
```

Stages run in dependency order, each in its own transaction, so a failure in
stage eight keeps stages one to seven and the re-run walks through them
reporting "found" until it reaches the one that failed.

| # | Stage | What it puts on the screens |
|---|---|---|
| 1 | `organisation` | Two open centres (Grras Jaipur, Grras Pune) and one closed (Udaipur); institution settings and branding; the global academic policy; policy overrides including a branch-level one; the holiday calendar |
| 2 | `people` | The roster below, with profiles, a custom role, a scope grant, notification preferences, referrals, and one refused action so the audit shows a denial |
| 3 | `courses` | Eight courses across draft/in review/published/archived with modules and lessons of every content type; the seventeen imported SITP courses given content and published; the question bank |
| 4 | `batches` | Batches in every status across both centres, timetables, generated classes including one that started today, and enrolments in every status |
| 5 | `fees` | Fee plans, payments across twelve weeks and every method, discounts, a void, and dues in each ageing bucket |
| 6 | `academics` | Registers with a spread of attendance rates, corrections, daily status reports in every review state, lesson progress, trainer requirements |
| 7 | `teaching_ops` | Assignments, assessments, projects, exams and attempts, completions and certificates — including revoked and superseded |
| 8 | `work` | Activities in all twelve statuses, performance reviews and feedback, risk states, saved filters, export jobs, a populated recovery bin |
| 9 | `comms` | Announcements for every audience, discussion threads, message templates and deliveries, automation runs, forms |
| 10 | `finish` | Clears the cache, abandons the run's outbox, prints the two summary tables |

### Who to sign in as

Every account below shares the one password. The centre matters: a manager and
a counsellor see only their own centre, so signing in as the Pune manager is
how the branch scoping shows itself.

| Role | Centre | Email | Name |
|---|---|---|---|
| superadmin | every | `owner@grras.com` | Rajesh Sharma |
| admin | Jaipur | `admin@grras.com` | Anjali Mehta |
| admin | Pune | `admin.pune@grras.com` | Nikhil Joshi |
| manager | Jaipur | `manager@grras.com` | Kavita Rathore |
| manager | Pune | `manager.pune@grras.com` | Sanjay Deshmukh |
| counsellor | Jaipur | `counsellor@grras.com` | Pooja Agarwal |
| counsellor | Pune | `counsellor.pune@grras.com` | Sneha Kulkarni |
| trainer | Jaipur | `trainer@grras.com` | Vikram Shekhawat |
| trainer | Pune | `ankit.kulkarni@grras.com` | Ankit Kulkarni |
| student | Jaipur | `student@grras.com` | Aarav Mehta |

Plus, for the states a demo needs to show on purpose: `manager2@` has never
verified their email, `placement@` holds a custom role, `sameer.bhatt@` is a
trainer who is not accepting assignments, `deepak.purohit@` has left, and one
student never enrolled. A hundred more students fill the rosters; the command
prints the whole list at the end of every run.

The trainer to demonstrate teaching with is `trainer@grras.com`: the stage
gives them an active batch whose class **started earlier today**, which is what
makes the register markable and the day's report writable.

---

## 3. Production

### The showcase cannot run there, by design

`ALLOW_DEMO_SEED` is false in production settings and every seed command
refuses before it touches anything. That is not an obstacle to work around — a
production database holding invented students is a data problem that takes
weeks to unpick. Show the product on staging, which is what staging is for, and
let production start with real records entered through the interface.

If a production-shaped environment with invented data is genuinely wanted for
sales, add it as its own environment (`docs/environments.md` §Adding a new
environment) with its own database and secrets, and keep `ALLOW_DEMO_SEED` true
only there.

### What to set before a production deploy

`.env.production.example` is the full template and every value marked REQUIRED
there must come from the secret manager. The list below is the same thing
ordered by what will stop the application booting, because the settings fail
closed: a missing required value refuses to start rather than degrading
quietly.

**Refuses to boot without these**

| Variable | What it must be |
|---|---|
| `DJANGO_SECRET_KEY` | Unique to production, ≥50 characters, never a staging value. `python -c "import secrets;print(secrets.token_urlsafe(64))"` |
| `DJANGO_ALLOWED_HOSTS` | The exact API hostnames. No wildcard. |
| `CSRF_TRUSTED_ORIGINS` | Exact origins with scheme, matching where the browser app is served. |
| `CORS_ALLOWED_ORIGINS` | The same origins. |
| `FRONTEND_BASE_URL` | Where emailed reset and verification links point. Must share a registrable domain with the API — session cookies are `SameSite=Lax`. |
| `DATABASE_URL` | PostgreSQL, pointed at the **application** role from `infra/db/least-privilege.sql` (reads and writes rows, cannot change the schema). Migrations run separately. |
| `CACHE_URL` | Redis. Mandatory: throttling counters must be shared across workers. |
| `CELERY_BROKER_URL` | A **different** Redis database from the cache, so a cache flush cannot empty the queue. |
| `EMAIL_HOST` | Required whenever the backend is SMTP, which production's is. Without mail nobody can reset a password. |
| `DEFAULT_FROM_EMAIL` | The sender on every message. |
| `MFA_ENCRYPTION_KEY` | A Fernet key, unique to production. **Never rotated without a plan** — rotating it makes every enrolled authenticator unreadable, and it is in no database dump. `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `AWS_STORAGE_BUCKET_NAME` | Required with `FILE_STORAGE_BACKEND=s3`. Private bucket, versioning on. Student files must not sit on a container volume. |

**Set explicitly, and check the value**

| Variable | Production value | Why |
|---|---|---|
| `DJANGO_ENV` / `DJANGO_SETTINGS_MODULE` | `production` / `config.settings.production` | The settings refuse to load if these disagree. |
| `DATABASE_SSL_MODE` | `require` | Staging uses `disable`; copying it forward sends credentials in clear. |
| `DATABASE_CONN_MAX_AGE` | `60` | **Not** `CONN_MAX_AGE`. The template's old spelling was never read by the code. |
| `CELERY_TASK_ALWAYS_EAGER` | unset or `false` | True runs queued work inside the request; the settings reject it. |
| `SECURE_SSL_REDIRECT` | `True` | Staging sets `False` because Caddy already serves HTTPS only. |
| `SECURE_HSTS_SECONDS` | `63072000` | Two years with subdomains and preload. Start lower on a brand-new domain: HSTS cannot be withdrawn quickly. |
| `NUM_PROXIES` | The real number of proxies in front | Too high lets a client spoof its own address, defeating rate limiting and audit attribution. |
| `API_DOCS_ENABLED` | `False` | The schema describes every endpoint to anyone who asks. |
| `DJANGO_LOG_FORMAT` / `DJANGO_LOG_LEVEL` | `json` / `INFO` | Machine-readable logs. |
| `AWS_S3_REGION_NAME` | The bucket's region | Optional in code, required by the template. |
| `AWS_S3_ENDPOINT_URL` | empty on AWS | Set only for an S3-compatible provider. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | prefer unset | Use an instance role. If they must exist, rotate them on a schedule. |
| `UPLOAD_SCANNER` | `disabled` until a scanner exists | An unreachable scanner refuses uploads. Only set `UPLOAD_SCAN_FAIL_OPEN=true` with a written reason. |
| `SENTRY_DSN` / `APP_VERSION` | if error reporting is wanted | PII is never sent; `APP_VERSION` becomes the release tag. |
| `DJANGO_TIME_ZONE` | leave at `Asia/Kolkata` | Weekly reporting buckets are computed in it. |
| `BACKUP_S3_BUCKET` / `BACKUP_KEEP_DAYS` | set both | Staging has neither, so its nightly dumps never leave the host. Production must copy them off. |

**Must not be set in production**

- `DEMO_USER_PASSWORD` — has no meaning there; the seeders refuse anyway.
- `VERIFY_ALLOWED_EMAIL_DOMAINS` — the reserved-domain check is a staging
  safeguard; production holds real addresses by definition.
- `DEBUG` — not configurable; production hard-codes it off.

**Frontend build arguments** (`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_APP_ENV`,
`INTERNAL_API_BASE_URL`) are baked in at build time, so the production image
must be built with the production origin. Changing them later means rebuilding,
not restarting.

### Before the first production deploy

The release gate is `docs/RELEASE_READINESS.md`; nothing here replaces it. The
items it will not let pass and that are worth naming twice: a verified restore
from a real dump, the migration review, and a rollback plan that someone has
actually executed once against staging.

---

## 4. Undoing a showcase run

There is no unseed command, deliberately: a delete pass across thirty models
with protected foreign keys is how a demo environment loses real data. Restore
instead. `./scripts/backup.sh staging` runs first in every deploy, so the dump
from immediately before the run is on the host under `backups/`, and
`docs/erp/BACKUP_AND_RECOVERY.md` is the restore runbook.

Showcase rows are identifiable: every note, reason and description a stage
writes starts with `[showcase]`.
