# Release readiness

**Status: not production ready.** Five things a person must do first are listed
in [Remaining production tasks](#remaining-production-tasks). Everything the
code can settle on its own is settled and verified below.

Assessed 2 September 2026, against the local production-shaped staging stack.

---

## Summary

| | State |
| --- | --- |
| Build | Both production images build and run |
| Tests | 1,221 backend · 61 frontend unit · 69 end-to-end |
| Security | Every gate clean: bandit, pip-audit, npm audit, gitleaks, `check --deploy` |
| Performance | Profiled at 400 students; every report flat in query count |
| Migrations | 58, none destructive, fresh install and reverse both verified |
| Backups | Dump and restore verified, sequences included |
| Staging | Running, production-shaped, seeded with fake data only |
| Mandatory journey | Passes, three runs in a row |

---

## Build

Both images build from `infra/docker/` and run as unprivileged users. The
backend production target runs **gunicorn**, never `runserver`; the frontend
runs the Next.js standalone build.

The staging stack is what production will look like: gunicorn, `DEBUG=False`,
the full hardened settings, TLS in front, a Celery worker and scheduler, Redis,
PostgreSQL 17, and object storage over the S3 protocol.

---

## Tests

| Suite | Count | Where it is green |
| --- | --- | --- |
| Backend | 1,221 | 91% statement coverage |
| Frontend unit | 61 | |
| End-to-end suite | 68 | Local development stack: 68/68 |
| Mandatory journey | 1 | Clean staging, the production build: passes repeatedly |

```bash
npx playwright test                                    # the suite
E2E_RELEASE_JOURNEY=1 npx playwright test --project=release   # the journey
```

The journey is a separate run because it signs in about a dozen times: inside
the suite the credential rate limit is exhausted by the tests before it, and it
spends twelve minutes waiting out throttles that have nothing to do with what it
is testing. Alone it takes ninety seconds.

Running the whole suite against staging as well was not asked for, and doing it
anyway was worth it: the production build had never been opened in a browser
before this phase, and the first attempt found it did not work at all (see
*Content-Security-Policy* below). Three further environment differences came out
of it and are fixed — a sign-in assertion that waited for a greeting rather than
the session, a per-test timeout calibrated to the dev server, and no handling of
the rate limit. **61 of the 68 suite tests now pass on staging; seven do not.**
They are specs written against the development stack that remain sensitive to
it, and finishing that is unfinished work, recorded below rather than rounded
off.

### The mandatory journey (§15.2)

`frontend/e2e/release-journey.spec.ts` walks the whole chain in one test, and
has passed three consecutive times:

> admin signs in → creates a course, module and lesson → publishes all three →
> creates a batch → sets a timetable and generates classes → assigns a trainer,
> then reassigns → adds a student → enrols students → student signs in →
> starts learning and completes a lesson → trainer takes the register →
> assignment set, handed in, graded → weekly test created, results imported,
> student sees the mark → project set, handed in, reviewed → questions authored →
> examination published, sat, marked, released → completion evaluated and
> approved → certificate issued → **certificate verified from a signed-out
> browser**

Two deliberate notes on how it runs:

- It creates a student *and* enrols them, because those are the steps under
  test. The learning half then runs as a seeded student, because a newly created
  account has no usable password by design — §1 has the administrator send a
  set-password link rather than choose somebody's password for them. Weakening
  that to simplify a test would trade a real security property for convenience.
- It clears its own leftovers and archives everything it creates, so it can run
  against the same environment repeatedly.
- It signs in as `trainer3` and `student7`, which no other spec touches. The
  journey changes their world — it marks a register, hands work in, and finishes
  a course — and sharing fixtures with the rest of the suite left those specs
  looking at a register already taken and a student already complete.

---

## Security

Every gate, run on 2 September 2026:

| Gate | Result |
| --- | --- |
| `ruff check` / `ruff format --check` | Clean |
| `bandit` | Clean |
| `pip-audit` | No known vulnerabilities |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| `gitleaks` | No leaks |
| `manage.py check --deploy --fail-level WARNING` | Clean, production and staging |

Phase 9 covered OWASP ASVS-shaped verification: authentication, an
authorization matrix derived from the URL resolver (160 tests), private object
storage with signed URLs, data minimisation, audit completeness, dependency and
database security. `docs/security.md` is the detail.

### Verified secret handling

`make secrets` does two things: it scans, and it proves the files the scan skips
(`.env`, `.env.staging`) are genuinely git-ignored. Removing the `.gitignore`
entry fails the gate rather than quietly turning an allowlist into a hole —
checked by removing it and watching it fail.

---

## Performance

Profiled against 400 students, 16,000 attendance records and 3,200 marks
(`make seed-scale`):

| | Before | After |
| --- | --- | --- |
| `student_progress` report | ~7,400 queries | 42 |
| `batch_performance` report | 148 | 5 |
| Batch dashboard | 4,097 ms | 18 ms |
| Enrolment list | 34 queries | 9 |

`tests/test_performance.py` asserts the property rather than a number: the same
endpoint, five times the data, the same query count.

The scale dataset belongs in its own database. Twenty-four generated courses
push the demo courses off the first page of the paginated catalogue, and the
end-to-end suite — which finds them by name — then fails. `make seed-scale-flush`
removes it.

---

## Migrations

`./scripts/check_migrations.sh staging`, last run clean:

```
1. No model change is unmigrated — the models and the migrations agree
2. Fresh installation — applied 76, pending 0
3. Reverse and re-apply — reversed assessments to zero, re-applied
4. Destructive operations — none in the history
```

No migration in this project removes or renames anything, so the previous
application version runs against the current schema and a rollback is a
rollback. `docs/operations.md` has the three-release pattern for the day that
changes.

---

## Backups

`./scripts/backup.sh staging --verify` dumps, restores into a scratch database,
counts what arrived, prints every identifier sequence, and drops the scratch
database. Verified:

```
users 41 · courses 44 · batches 38 · enrolments 72 · attendance 93
assessment marks 21 · certificates 3 · audit entries 1272
student_public_id_seq at 40 · certificate_number_seq at 3 · (all 19 sequences)
```

The sequences are checked because they are the failure that looks like success:
a restore with every table and no sequences hands the next student an identifier
somebody already has, and nothing complains until two people hold `GRS-S-00041`.

Not covered: object storage. Student files live in S3, so a database dump does
not contain them. Bucket versioning is the mechanism and no bucket exists yet.

---

## Staging

```bash
make staging-up          # https://localhost:8443
make verify ENV=staging  # 19 checks
```

Production-shaped on a laptop: gunicorn, `DEBUG=False`, hardened settings, TLS
terminated by Caddy, Celery worker and scheduler, MinIO for object storage over
the S3 protocol.

Staging speaks https because the hardened settings mark the session cookie
`Secure` and a browser on plain http silently refuses to store it — sign-in
appears to work and the next request is anonymous. Terminating TLS was the
alternative to weakening the setting, which would have meant staging no longer
testing what production runs.

**Seeded with fake data only.** Every account is on a reserved, undeliverable
domain, and `verify_demo.sh` fails if one is not. No production data has ever
been copied here.

---

## What this phase found

The mandatory journey and the production build together found ten defects that
review had not. The three that mattered:

**The production build never hydrated.** `script-src 'self'` blocked Next.js's
inline bootstrap, so every page rendered and no form worked — no error, no
warning, nothing in a log. It had never been noticed because the end-to-end
suite had only ever run against the dev server, which takes an `'unsafe-inline'`
branch. Fixed with a per-request nonce and dynamic rendering, not by weakening
the policy.

**A stale CSRF token after sign-out.** Django rotates the token when a session
ends, so the first action after signing back in failed once, then worked. The
client now refreshes and retries exactly once, for exactly that error.

**A suite that only worked on one server.** Nine copies of a sign-in helper all
waited for a greeting that a server-rendered page delivers a beat late, so
twenty-four tests failed on staging and none locally. Now one shared helper that
waits for the session, and waits out the rate limit rather than asking for it to
be raised.

**Two dead client functions.** `generateSessions` and `setLessonCompletion`
existed, were typed, and had no caller — so an administrator could set a
timetable and never turn it into classes, and a student could read a lesson and
never mark it done. Lesson completion feeds course completion, so the progress
system counted something no student could produce.

The rest: `on_holiday` documented in the API schema and never returned; a
cancelled batch still putting classes on a trainer's day, above the real one;
`seed_academics` dying part-way on a batch with no timetable, leaving an
environment neither empty nor seeded; a worker healthcheck reporting a healthy
worker as unhealthy; no confirmation when assigning a trainer or enrolling a
student; a lesson editor whose submit button shared its name with the button
that opened it; `--flush` in the scale seeder that could not flush; SigV2 signed
URLs that modern AWS regions reject.

---

## Known limitations

| | Detail |
| --- | --- |
| No multi-factor authentication | Rate limiting and session controls only |
| No account lockout | Throttling only |
| No malware scanning | The hook exists, fails closed, and no scanner is configured |
| Object storage not backed up | Needs bucket versioning on a real bucket |
| Fee handling is a status only | As specified: no amounts, transactions or gateway |
| XLSX export not built | Exports are CSV |
| Certificates render one layout | Templates are configuration, not a designer |
| Google Forms is a link | No API integration; marks are imported |
| Seven E2E specs are dev-stack-specific | They pass locally and fail on staging; the shared sign-in helper fixed three classes of this and the rest is unfinished |

---

## Remaining production tasks

Each of these needs a person with access to something this project does not
have. Nothing here is blocked on code.

1. **Provision an S3 bucket.** No public read policy. The application refuses
   to boot with a public ACL configured, and refuses to sign URLs without
   expiry. Set `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`, and prefer an
   instance role over keys. Enable versioning — that is the file backup.
2. **Provision managed Redis**, and point `CACHE_URL` and `CELERY_BROKER_URL`
   at separate databases so a cache flush cannot empty the queue.
3. **Supply SMTP credentials.** Without mail nobody can reset a password, and
   the application refuses to start with the SMTP backend and no host.
4. **Create the database roles** from `infra/db/least-privilege.sql`, and give
   the application the `grras_app` URL — the one that cannot change the schema
   or edit the audit log.
5. **Push to a remote and let CI run.** The pipeline has never executed: this
   repository has no remote. Every gate in it has been run locally, which is not
   the same thing.

Until 1–5 are done, this is a verified staging system, not a production one.
It should not be labelled otherwise.
