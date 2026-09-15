# Architecture decision records — ERP platform

Each record: problem, options, chosen solution, reason, trade-offs, impact,
rollback. Numbered ADR-xx to keep them apart from the product decisions in
`docs/DECISIONS.md` (D-xxx), which they build on and never contradict.

Standing rules these decisions obey: session authentication only, no JWT
(D-002); capabilities not role checks (D-007); authorization is a queryset
first (architecture rule 2); business rules in services (rule 1); every
state change audited (rule 5); educational history never deleted (D-019).

---

## ADR-01 · Dynamic RBAC: rows for roles, code for the catalog

**Problem.** Roles and capabilities are Python constants (`accounts/roles.py`).
The brief wants an administrator to create roles and assign permissions
without a deploy, with locking and audit.

**Options.**
1. Move everything to the database, including the permission catalog.
2. Keep the catalog in code; move the *mapping* (role → permissions, scope,
   lock) to the database.
3. Keep everything in code, add a "custom role = base role ± list" JSON on
   the user.

**Chosen.** Option 2.

**Reason.** A permission only means something if a view checks it. Views
declare `Capability.X` today (71 of them), so the catalog *is* the code; a
row that no view checks is a lie an administrator would believe. Keeping the
enum authoritative and mirroring it into `Permission` rows (`is_system=True`,
synced by a management command run in a migration and asserted by a test)
gives the admin a real list while making it impossible to reference a
permission that does nothing. The *mapping* is where configuration lives.

**Design.**
- `Role(slug, name, description, kind, status, is_system, is_locked, …)`.
  `kind` is one of the six existing `UserRole` values and fixes the role's
  place on the ladder and its scoping behaviour (`is_unbounded`, per-record
  trainer/student rules). System roles are seeded 1:1 from the six kinds.
- `RolePermission(role, permission, scope, is_locked, granted_by)`.
- `User.role` (the kind) stays. `User.custom_role` FK (nullable) points at a
  custom role whose `kind` must equal `User.role`. Effective capabilities =
  the custom role's permission set if present, else the system role's.
- `has_capability(user, cap)` reads `resolved_capabilities(role_slug)` from
  the cache (`auth:roles` prefix, version-keyed; see ADR-14) and falls back
  to the code matrix if the table is empty (first boot, tests).
- Ladder rule kept: `can_grant_role` / `can_administer` compare *effective*
  sets, so a custom role wider than its granter cannot be handed out.
- Superadmin keeps `frozenset(Capability.values)` regardless of rows: the
  one role that can never be locked out of a feature by configuration.

**Trade-offs.** Two sources to keep equal (enum, rows) — mitigated by the
sync command and a test. A custom role cannot change its *kind*'s per-record
rules (a trainer-kind role still sees only assigned batches) — that is the
point: the kind is the security floor, the rows adjust the ceiling.

**Impact.** Additive migration; every existing test passes because the seeded
rows reproduce the matrix exactly. Frontend `lib/capabilities.ts` unchanged.

**Rollback.** Set `DYNAMIC_ROLES_ENABLED=false`: `has_capability` reads the
code matrix only. Tables can stay.

---

## ADR-02 · Scopes are a narrowing on top of the kind, never a widening

**Problem.** The brief lists eight scopes. Today scope is implicit: unbounded
(admin, superadmin) vs branch-bounded (manager, counsellor) vs assigned
(trainer) vs own (student).

**Options.**
1. Replace the implicit rules with a scope column consulted everywhere.
2. Keep the implicit rules as the floor; add an explicit scope that can only
   narrow.
3. Scope per user rather than per permission.

**Chosen.** Option 2, with scopes `all`, `branch`, `assigned`, `own`.

**Reason.** Every `access.py` already encodes the narrowest safe reading for
each kind. A configured scope that could *widen* would turn a typo into a
data leak; one that can only narrow cannot. `COURSE` and `BATCH` are
expressed as `assigned` plus the assignment records that already exist
(`CourseAssignment`, `Batch.trainer`) and a new `ScopeGrant(user, batch|course)`
for staff who are not trainers. `DEPARTMENT` is not built (no entity; see
gap matrix). `SELF` and `OWN` are the same thing here and are spelled `own`.

**Design.** `scope_for(user, capability)` returns the effective scope =
min(kind floor, configured). `scope_to_branch` becomes
`scope_for_capability(queryset, user, capability, path=…)` which applies:
`all` → untouched (only if the kind is unbounded); `branch` → the existing
branch filter; `assigned` → the existing per-record filter plus `ScopeGrant`;
`own` → the caller's own rows. Each `visible_*` function names its capability.

**Trade-offs.** Touches every `access.py` (≈ 12 files). Done in one phase
with a sweep test per endpoint and scope.

**Rollback.** Delete `RolePermission.scope` values (all NULL = floor only).

---

## ADR-03 · Permission locking is enforced in the service, shown in the matrix

**Problem.** Some grants must not be removable by an ordinary administrator
(e.g. `record.purge` from superadmin, `audit.view` from admin).

**Chosen.** `RolePermission.is_locked` + `Permission.is_lockable`. Only a
superadmin with a step-up (ADR-06) may lock, unlock, or remove a locked
grant. The matrix shows five states: explicit, inherited (from the kind's
seeded set), locked, denied, system. Every change writes an audit row with
the before/after set.

**Rollback.** Locks are rows; removing them restores today's behaviour.

---

## ADR-04 · Policy engine: one table for the new categories, the academic table stays

**Problem.** Sixteen policy categories; two already exist with their own
shape (`AcademicPolicy` in two layers, `SystemSetting` singleton).

**Options.**
1. One generic key/value table for everything, migrate the two into it.
2. A generic table for the new categories; leave the two alone.
3. A typed table per category.

**Chosen.** Option 2.

**Reason.** D-024 and D-032 chose named columns for academic rules on
purpose: the resolver, the admin form and the API cannot drift. That still
holds. The new categories (auth, password, MFA, session, activity,
performance weights, risk, communication, export, deletion, approval, file
upload, notification) are read by new code, so a generic `Policy(category,
key, value JSON, scope global|branch, version)` with a **code-defined schema
registry** (`POLICY_SCHEMAS[category][key] = {type, default, min, max,
choices, critical}`) gives named, validated settings without a table per
category. `PolicyVersion` rows hold every prior value with who/why.

**Reads.** `policy(category, key, branch=None)` → branch override → global →
default; memoised per request like `policy_for`; cached under `policy:*`
(ADR-14) with `forget` on write.

**Critical policies** (flagged in the schema: MFA required roles, session
age, password rules, deletion rules) require a step-up and an explicit
confirmation string in the request.

**Rollback.** Defaults in the schema reproduce today's behaviour; deleting
rows returns to them.

---

## ADR-05 · Email OTP and TOTP are two factors on one session flow

**Problem.** No MFA exists. The brief wants email OTP, TOTP, recovery codes,
policy-driven requirement, and step-up.

**Chosen.**
- Login: password → if MFA is required by policy for the user's role *or*
  the user enrolled a device → the session stores `mfa_pending={user_id,
  expires}` and nothing else; the response says `{"mfa_required": true,
  "methods": [...]}`. `POST /auth/mfa/verify/` with a TOTP code, an email
  OTP, or a recovery code completes `login()`. Pending state expires in 5 min.
- Email OTP: `OneTimeCode(user, purpose, code_hash, expires_at, attempts,
  consumed_at, sent_to, ip)` — 6 digits from `secrets`, SHA-256 hashed with
  a per-row salt, 10-minute expiry, 5 attempts, resend after 60 s, at most
  5 per user per hour and 20 per IP per hour, consumed under
  `select_for_update`. Never logged (the scrubber already denylists `otp`).
- TOTP: `MfaDevice(user, secret_encrypted, confirmed_at, last_used_step)`
  using `pyotp`; the secret is encrypted with `MFA_ENCRYPTION_KEY`
  (Fernet, environment only). Replay is refused by remembering the last
  accepted time step. Ten recovery codes, hashed, single use.
- Step-up: `session["step_up_at"]`; a `require_step_up` permission checks it
  is within `policy("auth", "step_up_minutes")` (default 10). Obtaining it
  re-enters the password or a second factor.

**Reason.** Keeps D-002 (session only). No new auth scheme, one new pending
state.

**Rollback.** Policy `mfa.required_roles = []` and users can unenrol; the
flow degrades to today's login.

---

## ADR-06 · Sessions get an index, not a new engine

**Problem.** Session inventory and per-session revoke are required; the DB
session table is not indexed by user (today's revoke-all scans it).

**Chosen.** `UserSession(user, session_key_hash, ip, user_agent, device_label,
created_at, last_seen_at, revoked_at)` written at login, touched by
middleware at most once per five minutes. Revoke one = delete the Django
session row by key and stamp the record. Revoke all others = iterate the
user's records. Keep `django.contrib.sessions.backends.db`.

**Rollback.** The table is advisory; deleting it leaves login untouched.

---

## ADR-07 · Dynamic forms are versioned rows; values live with the record

**Problem.** Activity types need custom fields; students need custom fields;
published forms must be immutable and history must keep its version.

**Chosen.** App `forms`: `FormDefinition(slug, name, entity, status)`,
`FormVersion(definition, number, status draft|published|archived, published_at,
published_by, schema_hash)`, `FormField(version, key, label, type, required,
order, group, options JSON, validation JSON, help, visible_to_student)`,
`FormResponse(version, values JSON, content_type, object_id)`.
A published version is immutable: any edit creates the next draft. The
validator (`forms/validation.py`) is the one place that knows the 17 field
types. Core business fields stay typed columns (brief §20).

**Rollback.** Records keep their `FormResponse`; unused definitions are
soft-deleted.

---

## ADR-08 · The work engine is a new app named `work`, not `activity`

**Problem.** `apps/activity` already exists and is the *audit* review the
owner asked for on 14 September ("activity review"). The brief's "activity"
is structured student work. Same word, different thing (brief §62).

**Chosen.** New app `work` with `ActivityType`, `Activity`, `ActivityHistory`.
The API is mounted at `/api/v1/activities/` (the noun people use); the
audit feed stays at `/api/v1/activity/feed/`. Frontend labels: "Activities"
for work, "Activity review" for the audit feed.

**Lifecycle.** Twelve statuses from the brief with an explicit transition
table (as `dsr/services.py` does). Every transition writes `ActivityHistory`
and an audit row. `OVERDUE` and `MISSED` are set by a beat task, never by a
person; a person reopens (`REOPENED`) or cancels.

**Rollback.** App can be left installed with no types; nothing else depends
on it except the timeline source, which skips an empty source.

---

## ADR-09 · The timeline is a composed read model with cursor pagination

**Chosen.** `work/timeline.py` registers sources (enrolment, transfer,
attendance day, DSR, assessment result, assignment submission, project
state, activity, feedback, review, communication delivery, certificate),
each returning `TimelineEntry(occurred_at, kind, title, summary, href,
actor, id)` for one student within a window, through that source's own
`visible_*`. Pagination is by `(occurred_at, id)` cursor over a merged,
sorted window of at most 200 per source per page. Same pattern as
`dashboards/calendar.py`.

---

## ADR-10 · Performance is weighted, and every number carries its sources

**Chosen.** `student_performance` returns `components[]`, each `{key,
label, weight, value, contribution, sources[]}`; `overall_score` is the
weighted mean of components that have data. Weights from policy
`performance.weights` (defaults equal → identical to today's mean; test
pins the equality on the fixture). The activity component is the weighted
mean of completed activities' normalised scores, per type weight, and its
sources list each activity (type, score, date, trainer).

---

## ADR-11 · Risk stores its last verdict so change is an event

**Chosen.** `RiskState(enrollment, level, triggered JSON, computed_at)`;
recompute on the events that move the numbers (attendance marked, result
recorded, activity completed, submission graded) via a debounced task
`risk.recompute(enrollment_id)`; a level or set change emits
`RISK_CHANGED` to the automation engine and a notification kind. New rules:
activity (overdue count, last score), project (overdue), placement
(placement-category activity scores). Rule thresholds live in policy
category `risk`; the four legacy academic fields remain the defaults.

---

## ADR-12 · Communication: one `Delivery` row per message per channel

**Chosen.** App `communication`: `MessageTemplate` + `TemplateVersion`
(channel, subject, html, text, variables allowlist, provider_template_id,
language, status draft|approved|published), `Delivery(channel, recipient,
template_version, variables, state, attempts, provider_message_id, error,
related object)`. Rendering substitutes allowlisted variables only — no
expressions, no filters — and HTML passes through a sanitiser; D-051's
concern (templates as an injection surface) is answered by never evaluating
template text. Code templates remain the fallback when no published row
exists for a kind. Email transport reuses the outbox; WhatsApp goes through
`providers.WhatsAppProvider` (Null by default; Meta Cloud when configured).

---

## ADR-13 · Automation is data evaluated by a fixed vocabulary

**Chosen.** `AutomationRule(trigger, conditions JSON, actions JSON, status,
version)`. Conditions: a list of `{path, op, value}` over an allowlisted
context per trigger (`activity.score`, `activity.type`, `risk.level`, …),
ops `eq ne lt lte gt gte in contains`. Actions: `create_activity`,
`send_notification`, `send_email`, `send_whatsapp`, `create_review`,
`flag_risk`, each with a typed parameter schema. Runs are rows
(`AutomationRun`) with an idempotency key `(rule, trigger, object, occurrence)`
and a depth counter: an action's own trigger runs at most 3 levels deep.
Executed by Celery; a failed action is a failed run, never a failed request.

---

## ADR-14 · Authorization caches are version-keyed and bumped on commit

**Chosen.** Roles, permissions, policies, published forms and templates are
cached with `apps/common/caching.remember` under versioned prefixes. Every
write calls `forget(prefix)` inside `transaction.on_commit`. A read that
races the bump sees the old version key at worst for the duration of one
request. Never cache a *denial* longer than a *grant* — both share the key.
TTLs: roles 10 min, policy 10 min, forms/templates 1 h, dashboards 1 min.

---

## ADR-15 · Exports, imports and searches stay inside `visible_*`

Every export re-scopes to the requester in the worker (existing `_rescope`);
global search federates only through each type's `visible_*`; imports
create through the same services the screens use. No parallel data path.

---

## ADR-16 · Migrations are additive in this programme

Every phase adds tables or nullable columns. No rename, no drop. Anything
that would need a destructive change follows the three-release pattern in
`docs/operations.md` §1 and is listed in the phase plan as such. Fresh
install and reverse are proven by `scripts/check_migrations.sh` per phase.

---

## ADR-17 · Background jobs are idempotent and bounded

Every new task: re-reads its row and checks state before acting (as
`send_queued_email` does), has soft/hard limits under the global 240/300 s,
retries with exponential backoff at most 5 times, and distinguishes
transient (`retry`) from permanent (`fail`, recorded) errors.

---

## ADR-18 · API versioning stays at `/api/v1/`

New endpoints are added under v1; nothing existing changes shape. A field is
only ever added. If a breaking change is ever needed, `/api/v2/` mounts
beside v1 for one release.

---

## ADR-19 · Backups add the bucket, not a new tool

`scripts/backup.sh` keeps doing the database. A new `scripts/backup-media.sh`
mirrors the MinIO/S3 bucket with `mc mirror` / `aws s3 sync` to a second
prefix, on the same cron; verification lists and hashes a sample.
RPO 24 h, RTO 2 h, documented drill in `BACKUP_AND_RECOVERY.md`.
