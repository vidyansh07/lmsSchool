# Release readiness

**Status: not production ready.** Five things a person must do first are listed
in [Remaining production tasks](#remaining-production-tasks). Everything the
code can settle on its own is settled and verified below.

Assessed 2 September 2026, against the local production-shaped staging stack.
Re-measured 18 September 2026 at the close of the 25-phase ERP programme
(Phase 25, `docs/erp/IMPLEMENTATION_PLAN.md` row 25) — the Tests and Security
sections below carry today's real, freshly-run numbers rather than 2
September's, and a new [ERP programme](#the-erp-programme-25-phases)
section summarises what the 24 phases since built. Everything else in this
document (Performance, Migrations, the Staging recipe) is unchanged from 2
September and was not re-measured in this pass.

---

## Summary

| | State |
| --- | --- |
| Build | Both production images build and run |
| Tests | 3,455 backend (3,451 passed, 4 skipped, 0 failed) · 1,153 frontend unit · 99 end-to-end |
| Security | Every gate clean: bandit, pip-audit, npm audit, gitleaks, `check --deploy` — re-run 18 September |
| Performance | Profiled at 400 students; every report flat in query count |
| Migrations | 156 across 25 apps, none destructive |
| Backups | Dump and restore verified, sequences included; object storage now covered too (Phase 23 — see Known limitations) |
| Staging | Running, production-shaped, seeded with fake data only |
| Mandatory journey | Passed repeatedly through Phase 24's own staging verification; not re-run in this pass (no live stack stood up for Phase 25) |

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
| Backend | 3,455 (3,451 passed, 4 skipped) | `pytest` with no path filter (`tests/` plus every `apps/*/tests/` directory, matching `pyproject.toml`'s own `testpaths`) — run 18 September, 0 failed. (An earlier pass of this same phase reported 3,448/3,444: that number came from a narrower, four-app subset used by the fast mid-phase verify checklist, mislabelled as the full suite; `pytest --collect-only` confirms 3,455 is the genuine full collection.) |
| Frontend unit | 1,153 | `npx vitest run`, 128 files — run 18 September, 0 failed |
| End-to-end suite | 99 (98 in the default project, 1 gated) | Typechecks (`tsc --noEmit`) and lints clean, and every spec lists correctly under Playwright; not re-run against a live stack in this pass — see the note below |
| Mandatory journey | 1 | Verified on staging through Phase 24 (`docs/FEATURE_STATUS.md`'s per-phase "Last verified" rows); not re-run in this pass |

The backend and frontend unit counts above are this phase's own fresh,
complete run — every test, no subset. The end-to-end count is real (it is
what exists and is registered in the repository today, confirmed by
`playwright test --list`), but Phase 25 did not stand up a live
frontend+backend+worker stack to execute it against: doing so from this
worktree risked colliding with the concurrent session already running the
project's own `docker compose` stack in `/Users/vidyansh/grras/lms` (see
`docs/erp/AGENT_PLAYBOOK.md`'s isolation rule). The seven new specs this
phase adds (`crawl.spec.ts`'s six role-crawls, plus three focused ERP
journeys — see [The ERP programme](#the-erp-programme-25-phases)) follow
this suite's own established conventions (`e2e/helpers.ts`'s `signIn`, the
same demo accounts, `test.skip(!E2E_DEMO_PASSWORD, ...)`) and are ready for
the same staging run every other phase's specs already go through.

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

*(That 61/68 figure is this section's own 2 September measurement, against
the staging stack of that date — it predates every ERP phase and was not
re-run for Phase 25; see the Tests section above for what this phase did
re-measure.)*

### The mandatory journey (§15.2)

`frontend/e2e/release-journey.spec.ts` walks the whole chain in one test, and
had passed three consecutive times as of 2 September:

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

**Since 2 September:** the file itself is unchanged — no ERP phase edited
it — and each phase's own staging deploy included a live smoke check of the
endpoints that phase touched (`docs/FEATURE_STATUS.md`'s per-phase "Manual
verification" column), though not a re-run of this specific spec. Phase 25
did not re-run it either (no live stack stood up in this pass — see the
Tests section above); it remains the mandatory gate for whoever next deploys
this branch, unchanged in content from the three passes above.

---

## Security

Every gate, re-run 18 September 2026 (originally 2 September; every result
below is this phase's own fresh run, not carried forward):

| Gate | Result |
| --- | --- |
| `ruff check` / `ruff format --check` | Clean, `apps`/`tests`/`config` |
| `bandit -r apps config manage.py` | Clean — 0 issues (undefined/low/medium/high all 0), 65,420 lines scanned |
| `pip-audit -r requirements/dev.txt --strict` | No known vulnerabilities found |
| `npm audit` | 0 vulnerabilities |
| `gitleaks detect` | No leaks — 125 commits scanned |
| `manage.py check --deploy --fail-level WARNING` | Clean, production settings |

`gitleaks` is now installed via Homebrew (`which gitleaks` →
`/opt/homebrew/bin/gitleaks`, v8.30.1) rather than only available inside CI's
own image — confirmed as part of this phase, per the phase brief's own
instruction to check.

Phase 9 covered OWASP ASVS-shaped verification: authentication, an
authorization matrix derived from the URL resolver (160 tests), private object
storage with signed URLs, data minimisation, audit completeness, dependency and
database security. `docs/security.md` is the detail. Phase 24 (17 September)
added a second pass specifically over the ERP surface:
`docs/erp/SECURITY_DECISIONS.md`'s eleven-row threat table walked with real tests,
`backend/tests/test_erp_security_sweep.py` and `test_concurrency.py`, and a
mechanically-generalized mass-assignment sweep — see
[The ERP programme](#the-erp-programme-25-phases) below.

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

This section (`./scripts/backup.sh staging --verify`, the database) is
unchanged from 2 September and was not re-run in this pass. Object storage
— not covered by a database dump, since student files live in S3 — was the
gap noted here on 2 September; Phase 23 (17 September) closed it for real
(`scripts/backup-media.sh`, bucket versioning confirmed live on staging).
See [Known limitations](#known-limitations) and
[The ERP programme](#the-erp-programme-25-phases) for what that covers and
what is still a human-run drill rather than automated.

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
| MFA is opt-in, not enforced | Phase 5 (`apps/accounts/mfa.py`, `MfaVerifyView`) built and deployed real MFA — TOTP enrolment, email OTP, and ten single-use recovery codes, reachable at `/settings/security` and enforced on login via the pending-MFA session flow when a user has enrolled; policy-driven forced enrolment (`mfa_required_roles`) is wired but no role has been put in the policy yet, so nobody is required into it today |
| No account lockout | Throttling only |
| No malware scanning | The hook exists, fails closed, and no scanner is configured |
| Object storage backup drills not yet run for real | No longer "not backed up" — Phase 23 (17 September) built and deployed the real mechanism: `scripts/backup-media.sh` mirrors the bucket with a SHA-256 comparison of actual bytes on both sides, `manage.py export_configuration` covers the seven non-media categories a database dump alone would miss, and staging's own bucket is confirmed versioned (`storage-init`'s logs read `versioning is enabled`). What remains is two specific drill-log rows in `docs/erp/BACKUP_AND_RECOVERY.md`, deliberately left for a human to run rather than performed unattended: the first Sunday cron-verified scratch restore (installed, due 20 September) and a live-database-restore-plus-new-host-disaster-recovery drill (provisioning infrastructure and repointing DNS — genuinely destructive/costly, the one standing pause point in the whole 25-phase programme) |
| Fees are a ledger, not a gateway | Agreed amounts, payments and receipts are recorded by hand at the desk; nothing moves money |
| XLSX export not built | Exports are CSV |
| Certificates render one layout | Templates are configuration, not a designer |
| Google Forms is a link | No API integration; marks are imported |
| Seven E2E specs are dev-stack-specific | They pass locally and fail on staging; the shared sign-in helper fixed three classes of this and the rest is unfinished |

---

## The ERP programme (25 phases)

Everything above this section describes the base LMS as it stood on 2
September 2026. Between then and 18 September,
`docs/erp/IMPLEMENTATION_PLAN.md`'s 25-phase programme built the ERP layer
on top of it: capability-based
authorization and a role builder (1–2), step-up and MFA (4–6), configurable
policies (3), dynamic forms (8), the activity/work engine (9), a composed
timeline and Student 360 (10–11), a weighted performance and risk engine
(12–13), an automation rule engine (14), duplicate-aware admissions and
per-enrolment fees (15–17), manager/counsellor/trainer dashboards (16–18),
a communication center with templates and delivery tracking (19), background
exports (20), a caching and authorization-hardening sweep (21), performance
hardening with flat-cost tests (22), backup and recovery (23), a security
and regression sweep (24), and this phase — production readiness (25). One
row per phase, with its own tests, security checks and staging verification,
is in `docs/FEATURE_STATUS.md`'s "Phase 14 — ERP platform" table.

**What the adversarial-review process actually caught.** Phase 24 is the
clearest concrete example: its own review found a real concurrency bug in
`apps.performance.services.recompute_risk` (two callers reaching a brand-new
enrolment's first-ever risk computation at once could both lose a race on the
same `IntegrityError`), got it fixed with a retry that re-enters and finds
the already-committed row, added 48 new tests to prove it (and the other ten
rows of `docs/erp/SECURITY_DECISIONS.md`'s threat table), and had the fix
independently re-verified live on staging afterward. This phase's own audit
found two smaller examples of the same discipline paying off: writing
`tests/test_erp_journey.py` (the §103 gate test below) surfaced a real,
previously-untested bug in `apps.automation.evaluator._form_context` — a
`decimal` form field's value is stored as a string
(`apps.forms.validation._validate_decimal`), and an uncoerced numeric
condition against it raised `TypeError`, which `evaluate_condition` silently
treats as "condition false" — meaning the seeded "Communication practice
after a weak mock" automation rule could never have fired in production.
Auditing the export jobs panel's empty/error test coverage surfaced a second
one: `ExportJobsPanel` never cleared its `error` state before a retry's
fetch, so a Retry that actually succeeded still rendered the old error
forever. Both are fixed, both now have a regression test, in this phase's
own diff.

**What is still a human-supervised action, not a gap.** Phase 23 built the
real backup-and-recovery mechanism for object storage (see Known
limitations above) but deliberately left two `docs/erp/BACKUP_AND_RECOVERY
.md` drill-log rows unfilled rather than run them unattended: the first
Sunday cron-verified scratch restore (due 20 September) and a live-database
plus new-host disaster-recovery drill. This is the one standing pause point
across the whole 25-phase programme — everything else in Phase 23 was built
and proven against isolated scratch database/bucket stacks first.

**This phase's own gate.** `tests/test_erp_journey.py` walks
`docs/erp/USER_JOURNEYS.md` §7's own named chain — a trainer completing a
weak mock interview through to a manager's approval, performance and risk
recomputing, the real seeded automation rule firing, and every step
surviving a form version 2, the trainer leaving and the batch ending — in
one test, through the real service functions, against the real seeded
catalog rather than a lookalike fixture. It is `IMPLEMENTATION_PLAN.md` row
25's own named gate, and it passes.

**DECISIONS reconciliation.** Row 25's deliverables include "DECISIONS
entries", so every `D-NNN` citation across `docs/*.md` and `docs/erp/*.md`
was extracted and checked against `docs/DECISIONS.md`'s own headings:
127 distinct numbers cited, all 127 defined, zero cited and undefined.
Nothing was missing, so there was nothing to add — checked, not skipped.

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
5. **Make CI green.** The original task here was "push to a remote and let CI
   run"; that is done — the repository is on GitHub and the workflow runs on
   every push. On `feat/erp-foundation` it fails before any job starts
   (GitHub reports a workflow-file problem), so every gate has still only been
   proven locally. Triage the run, fix the workflow, and get one green run.

Until 1–5 are done, this is a verified staging system, not a production one.
It should not be labelled otherwise.
