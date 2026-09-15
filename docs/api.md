# API reference (Phase 3)

The authoritative contract is the generated OpenAPI document:

- Schema: `GET /api/schema/`
- Swagger UI: `GET /api/docs/` (local, development and staging; off in production unless enabled)

This page summarises the conventions and the endpoints that exist today.

---

## Conventions

**Base URL and versioning.** All application endpoints live under `/api/v1/`.
Health checks are unversioned so orchestrators need not track API versions.

**Content type.** JSON only, both directions.

**Authentication.** Session cookie. A browser client:

1. `GET /api/v1/auth/csrf/` — sets the `grras_csrftoken` cookie
2. `POST /api/v1/auth/login/` with the cookie value in the `X-CSRFToken` header
3. Subsequent requests send the session cookie; unsafe methods must keep
   sending `X-CSRFToken`

`credentials: 'include'` is required on every cross-origin request. The
bundled client (`frontend/lib/api.ts`) handles all of this.

**Errors.** Every failure returns:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The submitted data is invalid.",
    "details": { "email": ["Enter a valid email address."] },
    "request_id": "0f3c1a4b…"
  }
}
```

| `code` | HTTP | Meaning |
| --- | --- | --- |
| `validation_error` | 400 | Input rejected; `details` holds field errors |
| `bad_request` | 400 | Malformed request |
| `authentication_required` | 401 / 403 | No valid session |
| `authentication_failed` | 401 | Invalid credentials (never says which part) |
| `permission_denied` | 403 | Authenticated, but not allowed |
| `csrf_failed` | 403 | Missing or invalid CSRF token |
| `not_found` | 404 | No such resource |
| `method_not_allowed` | 405 | Wrong HTTP method |
| `conflict` | 409 | Conflicts with current state |
| `rate_limited` | 429 | Too many requests; `details.retry_after_seconds` |
| `invalid_token` | 400 | Password-reset or verification link is unknown, expired or already used |
| `invalid_transition` | 400 | The requested status change is not allowed from the current one |
| `schedule_conflict` | 409 | The class would double-book a trainer or a batch |
| `batch_full` | 409 | No seats left on the batch |
| `duplicate_enrollment` | 409 | The student already holds a live enrolment on that batch |
| `internal_error` | 500 | Unexpected failure; quote `request_id` to support |

**Pagination.** `?page=2&page_size=50`, capped at 100.

```json
{
  "count": 13, "page": 1, "page_size": 25, "total_pages": 1,
  "next": null, "previous": null, "results": [ ]
}
```

**Rate limits.** 60/min anonymous, 600/min authenticated, 10/min on
authentication endpoints (all configurable per environment).

**Request ids.** Every response carries `X-Request-ID`; error bodies repeat it
as `request_id`. A client-supplied `X-Request-ID` is honoured only when it
matches `^[A-Za-z0-9._-]{8,64}$`.

---

## Endpoints

### Health and discovery

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `/health/live/` | public — never touches the database |
| `GET` | `/health/ready/` | public — 200 healthy, 503 degraded |
| `GET` | `/api/` | public — version discovery |

### Authentication — `/api/v1/auth/`

| Method | Path | Access | Notes |
| --- | --- | --- | --- |
| `GET` | `csrf/` | public | Sets the `grras_csrftoken` cookie |
| `POST` | `login/` | public, rate limited | Identical 401 for every failure reason. On a correct password, when MFA applies (ERP Phase 5, ADR-05): `200 {"mfa_required": true, "methods": [...], "expires_in": 300}` instead of the signed-in user — see "Multi-factor authentication" below |
| `POST` | `logout/` | authenticated | Ends the current session |
| `POST` | `logout-all/` | authenticated | Revokes every session, including this one |
| `GET` | `sessions/` | authenticated | The caller's own active sessions — see "Session management" below |
| `DELETE` | `sessions/<id>/` | authenticated | Revoke one of the caller's own sessions |
| `POST` | `sessions/revoke-others/` | authenticated | Revoke every one of the caller's sessions except this one |
| `GET` | `me/` | authenticated | Current user plus their capability list |
| `PATCH` | `me/` | authenticated | First name, last name, phone — nothing else |
| `GET` | `me/email/` | authenticated | Email verification status |
| `POST` | `me/profile-image/` | authenticated | Multipart upload, re-encoded server-side |
| `DELETE` | `me/profile-image/` | authenticated | Remove the image |
| `POST` | `password/change/` | authenticated, rate limited | Requires the current password |
| `POST` | `password/reset/` | public, rate limited | Always 202, identical for unknown addresses |
| `POST` | `password/reset/confirm/` | public, rate limited | Single-use, expiring token |
| `POST` | `email/verify/` | authenticated, rate limited | Sends (or resends) the link |
| `POST` | `email/verify/confirm/` | public, rate limited | Single-use, expiring token |

### Users — `/api/v1/users/`

| Method | Path | Capability |
| --- | --- | --- |
| `GET` | `` | `user.view_any` |
| `POST` | `` | `user.create` |
| `GET` | `<id>/` | `user.view_any` |
| `PATCH` | `<id>/` | `user.update_any` (plus `user.change_role` to alter a role) |
| `POST` | `<id>/set-active/` | `user.set_active` |
| `GET` | `<id>/profile-image/` | any authenticated, active user |
| `DELETE` | `<id>/profile-image/remove/` | `user.update_any` |
| `GET` | `<id>/sessions/` | `session.view_any` — see "Session management" below |
| `DELETE` | `<id>/sessions/<session_id>/` | `session.revoke_any`, fresh step-up |

Listing supports `?search=`, `?role=`, `?is_active=`, `?is_email_verified=`,
`?joined_after=`, `?joined_before=`, `?ordering=` and pagination. Search matches
name, email, student ID and trainer ID.

### Students — `/api/v1/students/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `student.view_any` |
| `POST` | `` | `student.create` — creates the account and profile together |
| `GET` | `me/` | the signed-in student |
| `PATCH` | `me/` | the signed-in student, self-editable fields only |
| `GET` | `<id>/` | `student.view_any`, or the owner |
| `PATCH` | `<id>/` | `student.update_any`, or the owner (restricted fields) |
| `POST` | `<id>/fee-status/` | `student.set_fee_status` |
| `POST` | `<id>/fee-amount/` | `student.set_fee_status` — set or clear (`null`) the fee quoted at registration |

Filters: `?fee_status=`, `?qualification=`, `?city=`, `?is_active=`, `?search=`
(student ID, name, email, institution), `?institution=` (contains),
`?institution_kind=`, `?referred_by=<student id>`, `?ordering=`.

**The agreed fee.** `POST /students/` accepts a top-level `fee_amount` (rupees,
minimum 1000, two decimals) alongside `profile`; it is checked against
`student.set_fee_status` in the service, so creating a student and quoting a
fee are two permissions even though they arrive in one request. `null` means
"not decided"; zero is refused. Students read `fee_amount` on `me/` and cannot
change it — it is not in the self-editable set, and the strict serializer names
the field rather than ignoring it. Every change is audited with both values
(`student.fee_amount.changed`).

Every list row also carries the ledger's totals across the student's courses —
`fee_payable`, `fee_paid`, `fee_balance` and `fee_next_due_on` — computed as
subqueries in `apps/fees/queries.py`. `fee_status` is derived from the same
ledger after every change (see Fees below).

**College or employer.** `profile.institution` is the name; `profile.institution_kind`
says which it is (`college` | `employer` | empty). Both are self-editable, as are
`profile.job_title` (a working professional's designation) and
`profile.roll_number` (a college roll number — searchable, since for a college
batch it is often the only identifier a spreadsheet carries).

**Referrals.** A working professional who joins to learn a new skill is also a
channel, so a counsellor may record `profile.referred_by` — the id of the
existing student who sent them — at registration or later via `PATCH <id>/`.
Not self-editable (a student naming their own referrer is how a scheme gets
gamed), never the student themselves, and it survives the referrer's record
being removed. Reads carry `referred_by_label` ("Priya Shah (GRS-S-00012)");
the admin view adds `referrals_count`, and `?referred_by=` lists them.

### Trainers — `/api/v1/trainers/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `trainer.view_any` |
| `POST` | `` | `trainer.create` |
| `GET` | `me/` | the signed-in trainer |
| `PATCH` | `me/` | the signed-in trainer, self-editable fields only |
| `GET` | `<id>/` | `trainer.view_any`, or the owner |
| `PATCH` | `<id>/` | `trainer.update_any`, or the owner (restricted fields) |

Filters: `?skill=`, `?is_accepting_assignments=`, `?min_experience=`,
`?search=` (trainer ID, name, email, title), `?ordering=`.

### Categories — `/api/v1/categories/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user (retired categories are hidden from non-managers) |
| `POST` | `` | `category.manage` |
| `GET` | `<id>/` | `category.manage` |
| `PATCH` | `<id>/` | `category.manage` |

### Courses — `/api/v1/courses/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user — scoped to what they may see |
| `POST` | `` | `course.create` |
| `GET` | `mine/` | any signed-in user — courses they may author |
| `GET` | `<id-or-slug>/` | visible to the caller |
| `PATCH` | `<id-or-slug>/` | assigned author, or `course.update_any` |
| `POST` | `<id>/status/` | assigned owner or `course.publish_any` (an editor may only submit for review) |
| `GET` | `<id>/publish-checklist/` | anyone who may manage the course |
| `GET` | `<id>/thumbnail/` | visible to the caller |
| `POST` | `<id>/thumbnail/` | anyone who may manage the course |
| `GET` | `<id>/authors/` | `course.assign_authors` |
| `POST` | `<id>/authors/` | `course.assign_authors` |
| `DELETE` | `<id>/authors/<user_id>/` | `course.assign_authors` |
| `GET` | `<id>/modules/` | visible to the caller |
| `POST` | `<id>/modules/` | anyone who may manage the course |
| `POST` | `<id>/modules/reorder/` | anyone who may manage the course |

Listing supports `?search=` (title, code, description), `?category=<slug>`,
`?difficulty=`, `?status=`, `?visibility=`, `?mine=true`, `?ordering=` and
pagination. Filters never widen visibility: a student passing `?status=draft`
gets an empty page, not a draft.

### Modules — `/api/v1/modules/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `<id>/` | visible to the caller |
| `PATCH` / `DELETE` | `<id>/` | anyone who may manage the parent course |
| `POST` | `<id>/status/` | anyone who may manage the parent course |
| `GET` | `<id>/lessons/` | visible to the caller |
| `POST` | `<id>/lessons/` | anyone who may manage the parent course |
| `POST` | `<id>/lessons/reorder/` | anyone who may manage the parent course |

### Lessons — `/api/v1/lessons/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `<id>/` | course visible **and** content entitlement |
| `PATCH` / `DELETE` | `<id>/` | anyone who may manage the parent course |
| `POST` | `<id>/status/` | anyone who may manage the parent course |
| `GET` | `<id>/video/` | content entitlement — the only place a playback URL is issued |
| `GET` | `<id>/resources/` | content entitlement |
| `POST` | `<id>/resources/` | anyone who may manage the parent course (multipart upload) |
| `POST` | `<id>/resources/link/` | anyone who may manage the parent course |

### Resources — `/api/v1/resources/`

| Method | Path | Access |
| --- | --- | --- |
| `PATCH` / `DELETE` | `<id>/` | anyone who may manage the parent course |
| `GET` | `<id>/download/` | content entitlement; served as an attachment |

---

## Course access model

Three separate questions, answered by `apps/courses/access.py`:

| Question | Rule |
| --- | --- |
| **May I see this course exists?** | `course.view_any`, or an authoring assignment, or the course is published and its visibility is public/internal |
| **May I read its content?** | The above, **plus** — the lesson is a free preview, or the caller may manage the course, or (when `COURSE_CONTENT_REQUIRES_ENROLMENT` is off) any viewer |
| **May I change it?** | `course.update_any`, or an authoring assignment. Status changes additionally need `course.publish_any` or the `owner` assignment role |

Listing endpoints apply the first rule **as a queryset**, so paging, sorting and
filtering cannot reach past it. Detail endpoints resolve the record inside that
queryset, which is why a guessed identifier returns 404 rather than 403 — the
record is not merely forbidden, it is not in the caller's world at all.

### The enrolment seam

`COURSE_CONTENT_REQUIRES_ENROLMENT` is `False` in Phase 2 because enrolment does
not exist yet. Turning it on restricts non-preview lesson bodies, resources and
video to enrolled students; `access.is_enrolled` is the single function Phase 3
replaces. The gated behaviour is already covered by tests, so the switch is one
flag and one function body.

---

## Publishing workflow

```
DRAFT ──────────► IN_REVIEW ──────────► PUBLISHED ──────────► ARCHIVED
  │                   │                     │                     │
  └───────────────────┴─────────────────────┴─────────────────────┘
                    (back to DRAFT)
```

| From | To | Who |
| --- | --- | --- |
| draft | in_review | any assigned author |
| draft | published | owner or `course.publish_any` |
| in_review | published / draft | owner or `course.publish_any` |
| published | archived / draft | owner or `course.publish_any` |
| archived | draft | owner or `course.publish_any` |

Publishing is refused unless the course has a title, a description, at least one
published module and at least one published lesson inside it.
`GET /courses/<id>/publish-checklist/` returns the outstanding blockers.

Publishing gates the **public catalogue only**. A batch may run a course in
any state except `archived`, so a course can be created, a batch planned and
students enrolled while the lesson content is still being written.

Editing a published course is allowed but recorded: the audit entry carries
`published_course_edited` and the previous values of the changed fields.

---

## Content types

| Type | Requires | Notes |
| --- | --- | --- |
| `text` | `text_content` | Rendered as plain text, never as HTML |
| `video` | a `video` object | Metadata only; the URL comes from the playback endpoint |
| `document` | an attached file resource | Enforced at publish time |
| `external_link` | `external_url` | https only, opened with `noopener` |

Adding a type means one enum member plus one entry in
`LESSON_CONTENT_REQUIREMENTS`, and one branch in the lesson renderer.

---

### Batches — `/api/v1/batches/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user — scoped to what they may see |
| `POST` | `` | `batch.create` |
| `GET` | `<id>/` | visible to the caller |
| `PATCH` | `<id>/` | `batch.update_any` |
| `POST` | `<id>/status/` | `batch.update_any` |
| `POST` | `<id>/trainer/` | `batch.update_any` — refuses timetable clashes |
| `GET` | `<id>/roster/` | `enrolment.view_any`, or the batch's own trainer |
| `GET` | `<id>/schedules/` | visible to the caller |
| `POST` | `<id>/schedules/` | `batch.manage_schedule` |

Filters: `?status=`, `?course=<slug>`, `?trainer=<uuid>`, `?starts_after=`,
`?starts_before=`, `?search=` (code, name, course), `?ordering=`.

### Schedules — `/api/v1/schedules/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `<id>/` | visible through the parent batch |
| `PATCH` / `DELETE` | `<id>/` | `batch.manage_schedule` |

### Enrolments — `/api/v1/enrollments/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | scoped: a student sees their own, a trainer sees their batches', an administrator sees all |
| `POST` | `` | `enrolment.create` |
| `GET` | `mine/` | the signed-in student's own enrolments |
| `GET` | `<id>/` | the owner, the batch's trainer, or `enrolment.view_any` |
| `POST` | `<id>/status/` | `enrolment.update_any` |
| `GET` | `<id>/progress/` | the owner, the batch's trainer, or `enrolment.view_any` |

Filters: `?status=`, `?batch=<uuid>`, `?course=<slug>`, `?search=`.

For callers holding `fee.view_any`, list rows carry `fee_payable`, `fee_paid`,
`fee_balance` and `fee_next_due_on` for that enrolment (`null` when no fee has
been agreed yet); students never receive them.

### Centres — `/api/v1/branches/`

A branch is one centre. It bounds **people and classes** — `User`,
`StudentProfile`, `TrainerProfile` and `Batch` carry a `branch`; everything
else reaches a centre through one of them. It is not a tenant: courses, the
question bank and the academic policy are shared. `apps/organisation/scoping.py`
is the one place the rule lives and every `access.py` calls it.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `organisation.view_any` — a bounded caller sees only their own centre |
| `POST` | `` | `organisation.manage` (unbounded operators) — `code`, `name`, `city` |
| `GET` | `<id>/` | visible to the caller |
| `PATCH` | `<id>/` | `organisation.manage` |
| `POST` | `/api/v1/users/<id>/branch/` | `organisation.assign_users` — `branch_id`, `reason`; audited as its own action |

Rules: a **bounded** caller (any staff account with a branch) reads only that
centre — every other centre's id is a 404, never a 403 — and anything they
create is stamped with their own centre whatever they submit. An **unbounded**
caller (a superadmin with no branch) sees every centre and must name one on
create (`branch` on `POST /users/`, `/students/`, `/trainers/`, `/batches/`),
or the request is refused with "Choose the centre". A staff account with no
centre sees nothing. The data migration `organisation.0002` stamps every
existing row with a `MAIN` centre; the SITP importer takes `--branch`.

### Institution settings — `/api/v1/settings/`

One row with named columns (`apps/configuration`): `institution_name`,
`support_email`, `support_phone`, `notification_email_enabled`,
`export_retention_days`, `resource_upload_max_mb`. Each has a consumer —
notification templates and the support card, the email channel, the export
sweep, the shared upload guard.

| Method | Path | Access |
| --- | --- | --- |
| `GET` / `PATCH` | `` | `settings.manage` — administrators (deliberately not `platform.configure`, which is superadmin-only) |
| `GET` | `public/` | any signed-in user — the name and support contact only |

### Activity review — `/api/v1/activity/`

The audit log read as an administrator reads it. `audit.view` only.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `feed/` | `audit.view` — changes only, newest first; `?since=&until=&actor=&role=&kind=&branch=&search=`; paginated. Each row carries `summary` (a sentence written by the server), `kind` and `href` |
| `GET` | `scorecards/` | `audit.view` — `?period=today|week|month|custom&since=&until=&branch=&role=`; one card per active staff member, busiest first, with the figures that role is measured by and the fees they collected |

Noise — sign-ins, listings, downloads, verifications, refusals — is never
listed or counted. Views are not logged (owner's call), so they are not counted.

### Warnings — `/api/v1/warnings/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in staff member — their own warnings, most urgent first; a student gets `[]` |

Each warning: `kind`, `severity` (`error` today, `warning` this week, `info`
worth knowing), `label`, `count`, `href` (where to fix it) and up to five
`items` with their own `href`. Computed over the caller's visible querysets
and cached for a minute per person. Kinds: `fees_overdue`, `fees_missing`,
`batch_no_trainer`, `batch_seats`, `trainer_clash`, `batch_overrun`,
`dsr_missing`, `students_at_risk`, `not_enrolled`, `account_no_centre`,
`email_unverified`, `completions_pending`. The `warnings.weekly_digest` task
(Monday 08:00) sends every staff member their open warnings as a
notification, by email when their preferences allow.

### Roles and permissions — `/api/v1/roles/`, `/api/v1/permissions/` (ERP Phase 1)

Roles are rows (ADR-01 in `docs/erp/ARCHITECTURE_DECISIONS.md`); the
permission catalog stays the `Capability` enum, mirrored into rows by
`manage.py sync_permissions` (run by the seed migration and every deploy).
The six system roles are seeded from the code matrix, so nothing changed the
day the tables appeared. A custom role is built *from* a system kind and
holds a different set — never a wider reach than the kind (its scope floor).

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `roles/` | `role.view` — every role with `user_count`, `permission_count` |
| `POST` | `roles/` | `role.manage` (+ `permission.assign` to send `permissions`) — `slug`, `name`, `kind` (not superadmin), `description`, `permissions: [{code, scope?}]`; every code must be one the caller holds (403 otherwise, D-097); superadmin-only codes refused on other kinds; a scope wider than the kind's floor refused |
| `GET` | `roles/matrix/` | `role.view` — `{roles, permissions, cells[slug][code]}` with cells `explicit`, `inherited`, `locked`, `denied`, `system` |
| `GET` | `roles/<slug>/` | `role.view` |
| `PATCH` | `roles/<slug>/` | `role.manage` — `name` (custom only), `description`, `status` (custom only), `permissions` (full replacement; locked grants need a superadmin). Changing permissions or status ends the holders' sessions |
| `DELETE` | `roles/<slug>/` | `role.manage`; `reason`; refused for system roles (400) and while accounts hold it (409); reversible from the recycle bin |
| `GET` | `permissions/` | `role.view` — the catalog: `code`, `resource`, `action`, `category`, `description`, `is_lockable` |

`PATCH /users/<id>/` accepts `custom_role` (a slug of the same kind as
`role`, or null). Changing it needs `user.change_role`, is audited as
`user.role_changed` with `custom_role_from/to`, and cannot assign a role
holding more than the caller does. Every representation of a user carries
`custom_role` and `custom_role_name`.

Scopes on a grant (`all`, `branch`, `assigned`, `own`) are enforced (ERP
Phase 2, ADR-02): a role's grant may narrow below its kind's floor, never
widen above it. `apps.organisation.scoping.scope_to_branch` and
`scope_to_branch_or_shared` accept a `capability=` argument and consult the
configured scope before falling back to the branch wall — `assigned`
reaches the batches a trainer teaches plus any `ScopeGrant`; `own` reaches
only the caller's own rows, per endpoint. `DYNAMIC_ROLES_ENABLED=false`
makes every check read the code matrix alone, with no scope narrowing.

### Scope grants — `/api/v1/users/<id>/scope-grants/` (ERP Phase 2)

A batch or course an account may reach directly under an `assigned` scope,
without being its trainer.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `user.update_any`, within the caller's reach |
| `POST` | `` | `user.update_any`; exactly one of `batch` or `course`; resolved through the caller's own `visible_batches`/`visible_courses`, so another centre's id (for a bounded caller) is a 404 |
| `DELETE` | `<grant_id>/` | `user.update_any` |

### Step-up authentication — `/api/v1/auth/step-up/` (ERP Phase 2/4/5)

`POST` with **exactly one** of `{password}` or `{code}` re-proves identity
and marks the session fresh for ten minutes (`ADR-05`). Endpoints that need
it (locking a permission today; purge, MFA disable and critical policy
changes in later phases) answer `403 {"code": "step_up_required"}` when the
session's step-up has expired or never happened; the frontend opens a
dialog and retries once.

Phase 4 adds the `code` alternative: a 6-digit one-time code emailed to the
caller's own registered address, always via `POST` `request-code/` first.

| Method | Path | Access | Body / notes |
| --- | --- | --- | --- |
| `POST` | `step-up/request-code/` | Any active, signed-in user | No body. Emails a 6-digit code to the caller's own address, `202 {"detail": "..."}`. `429 rate_limited` (`{"error": {"code": "rate_limited", "details": {"retry_after_seconds": <n>}}}`) if: less than 60s since the caller's last code of this purpose; 5 already sent to this user in the last hour; 20 already sent from this IP (any user) in the last hour. Also throttled at the endpoint itself, 5 requests/min per IP (`throttle_scope="otp"`) |
| `POST` | `step-up/` | Any active, signed-in user | `{password}` **or** `{code}` (a 6-digit string), never both, never neither — `400` otherwise. A wrong password, or a wrong/expired/already-used/attempt-exhausted code, answers `403 {"code": "step_up_required"}`. Success: `204`, no body |

The code is single-use, expires in 10 minutes, and is void after 5 wrong
attempts — a 6th attempt fails even with the right code. It is delivered
inline (never through the notification outbox — the code *is* the
credential, per D-070) and is never returned by any endpoint, logged, or
written to the audit log; audit rows for `otp.sent`/`otp.verified`/
`otp.failed`/`otp.throttled` carry only the purpose (`step_up` today) and,
for a failure, a reason string. The same `OneTimeCode` model (a `purpose`
field, not a bespoke shape) is what Phase 5's pending-MFA sign-in reuses
with `purpose="login"` — nothing about this contract changes for that.

### Multi-factor authentication — `/api/v1/auth/mfa/…` (ERP Phase 5, ADR-05)

Two more factors beyond the password, and a third layer of step-up: a TOTP
authenticator app and ten single-use recovery codes, alongside the emailed
one-time code Phase 4 already built. `POST login/` never logs a person in
directly when their account has a confirmed device, or their role is on
`authentication.mfa_required_roles` and past `authentication.mfa_grace_days`
(a policy pair) — instead the session holds `mfa_pending` (a user id and a
5-minute expiry) and the response names which methods can complete it.

| Method | Path | Access | Body / notes |
| --- | --- | --- | --- |
| `POST` | `mfa/send-email-code/` | A pending sign-in, or any authenticated caller (step-up/enrolment) | No body. `204`. Same throttle (`otp`) and limits as `step-up/request-code/` |
| `POST` | `mfa/verify/` | A pending sign-in, or any authenticated caller | `{method: "totp"\|"email"\|"recovery", code}`. Completes the pending sign-in (calls `login()`, cycles the session key) or grants step-up, whichever context applies. `200` the signed-in user (`CurrentUserSerializer`, same shape `me/` returns) on success; `400 {"code": "invalid_code"}` on any failure — a wrong TOTP digit, an expired email code, and an already-used recovery code are all this one generic answer, never distinguishable from each other |
| `POST` | `mfa/totp/enrol/` | Any active, signed-in user | No body. `200 {secret_uri, secret, qr_svg}` — `qr_svg` is inline SVG markup encoding `secret_uri`. The only response that ever carries the secret; an unconfirmed device is silently replaced by calling this again. `409` if a device is already confirmed |
| `POST` | `mfa/totp/confirm/` | Any active, signed-in user | `{code}` (6 digits) against the pending device. `200 {recovery_codes: [...ten codes]}`, shown exactly once — the response is never retrievable again. `400` on a wrong code (the enrolment stays open to retry) or when there is no pending enrolment |
| `POST` | `mfa/totp/disable/` | Any active, signed-in user, fresh step-up | No body. Deletes the device and every recovery code outright — not a soft delete, since a "restorable" MFA bypass would be a real vulnerability. `204`. `403 step_up_required` without a fresh step-up; `400` if MFA was not enabled |
| `POST` | `mfa/recovery/regenerate/` | Any active, signed-in user, fresh step-up | No body. Invalidates every existing recovery code and issues ten new ones, shown exactly once, same shape as `totp/confirm/`. `403 step_up_required`; `400` if MFA was not enabled |

`available_methods` (what `login/` and the two send/verify endpoints ever
offer) always includes `email`; adds `totp` only with a confirmed device,
and `recovery` only while at least one unused code remains — in that order,
strongest first. TOTP is RFC 6238 (30s step, ±1 step tolerance), the shared
secret encrypted at rest (`MFA_ENCRYPTION_KEY`, environment-only) and never
logged, audited, or returned again after enrolment; replay of an
already-accepted step is refused. `mfa.enrolled`/`mfa.disabled` also email
the account (bypassing notification preferences — a security event, not a
subscription) and every verify/enrol/disable/regenerate outcome is audited
(`mfa.verified`/`mfa.failed`/`mfa.enrolled`/`mfa.disabled`/
`mfa.recovery_regenerated`), never with the code or secret in the context.

`GET me/` gains `mfa_enabled` (whether a confirmed device exists) so the
security settings screen can offer "set up" or "manage" without a second
call. The frontend's step-up dialog (`components/roles/step-up-dialog.tsx`)
still offers only password and email code — `POST step-up/` already accepts
`{method: "totp"|"recovery", code}` from any caller (see D-137), the UI
addition is left for a later pass.

### Session management — `/api/v1/auth/sessions/…`, `/api/v1/users/<id>/sessions/…` (ERP Phase 6, ADR-06)

`UserSession` is an index over Django's own session table, not a second
engine — written at every successful login (`LoginView`, and
`MfaVerifyView`'s login-completion branch), right after
`django.contrib.auth.login()` and the `cycle_key()` that follows it, since
the session key is only stable from that point on. Only a SHA-256 hash of
the key is ever stored (rule §13, same discipline as `OneTimeCode.code_hash`)
— nothing here can be turned into a working session by reading the database.

| Method | Path | Access | Body / notes |
| --- | --- | --- | --- |
| `GET` | `auth/sessions/` | Any active, signed-in user | `200 [{id, device_label, ip, created_at, last_seen_at, is_current}, ...]`, newest `last_seen_at` first. `is_current` compares the request's own session key hash |
| `DELETE` | `auth/sessions/<id>/` | Any active, signed-in user | Revokes one of the caller's own sessions: deletes the underlying Django session row (signing that device out immediately) and stamps `revoked_at`. `404` for an id that is not the caller's own or already revoked. `409 {"code": "current_session"}` for the session making *this* request — `POST logout/` is the right endpoint for that |
| `POST` | `auth/sessions/revoke-others/` | Any active, signed-in user | No body. Revokes every one of the caller's sessions except this one. `200 {"detail": "Signed out of N other session(s)."}` |
| `GET` | `users/<id>/sessions/` | `session.view_any` | Same row shape as above, for the named user. Resolved through the caller's own `visible_accounts`, so a cross-centre id is a `404` |
| `DELETE` | `users/<id>/sessions/<session_id>/` | `session.revoke_any`, fresh step-up | Same resolution as the `GET` above (a cross-centre id is `404` regardless of step-up state), then `403 step_up_required` without a fresh step-up. On success: `204`, the target user is emailed and the action audited (`session.revoked_by_admin`) |

**Device label.** A small heuristic over the user-agent
(`apps.accounts.sessions.device_label`) — recognises common browser/OS pairs
("Chrome on macOS", "Safari on iOS") and falls back to "Unknown device"
rather than ever showing the raw string, which can carry near-fingerprinting
detail. The full user-agent is still stored (`UserSession.user_agent`, never
returned by the API) since new-device detection needs it.

**`last_seen_at`.** Touched by `TouchSessionActivityMiddleware` on every
authenticated request, but the underlying `UPDATE` is guarded by `WHERE
last_seen_at < now() − 5 minutes` — a busy session's row is written at most
once every five minutes, not on every request, even though the guarded
statement itself still runs each time (accounted for as one more flat
per-request query in `tests/test_performance.py` and friends, the same way
the session and user reads already are).

**New-device detection.** At login, if this user has no prior `UserSession`
(revoked or not — a device seen once and later signed out is still known)
with the same recognised browser/OS pair from an IP in the same `/24`
(IPv4) or `/64` (IPv6) as the current request, the login is treated as a new
device: audited (`session.new_device_detected`) and emailed
(`session.new_device` — always delivered, bypassing notification
preferences, same as the MFA security emails).

**Existing session-wide revocation is unchanged and now stays in sync.**
`POST logout/` and `POST logout-all/` (`apps.accounts.services.
revoke_sessions`) still delete the underlying Django session row(s) exactly
as before; both now also stamp the matching `UserSession` row(s)
`revoked_at` so `GET sessions/` never shows a session that a different
endpoint already ended. Audit: the two per-session endpoints above use the
new `session.revoked` / `session.revoked_by_admin` actions; `logout-all/`
keeps its existing `auth.sessions.revoked`.

Policy keys `session.max_age_hours` (default 12, floor 1, ceiling 168) and
`session.idle_minutes` (default 0, meaning none) exist in the schema
registry for a future phase to enforce; this phase does not yet expire a
session on either basis.

### Permission locking — `/api/v1/roles/<slug>/permissions/<code>/lock|unlock/` (ERP Phase 2)

`POST`, superadmin only (`permission.lock`, seeded locked to that role
alone), and only with a fresh step-up. Freezes or unfreezes one grant so
an ordinary administrator cannot remove it from the Role Builder.

### Policies — `/api/v1/policies/` (ERP Phase 3, ADR-04)

A generic table (`apps.policies`) for the settings `AcademicPolicy` and
`SystemSetting` do not already own: `authentication`, `password`,
`session`, `risk`, `performance`, `communication`, `export`, `deletion`,
`approval`, `file_upload`, `notification`. Every key is declared in a
code-defined schema (`apps.policies.schemas.POLICY_SCHEMAS`) with its type,
default, bounds or choices, and whether it is `critical`. A row is either
institution-wide (`scope=global`) or one centre's override
(`scope=branch`); resolution is branch override, then global, then the
schema default (`apps.policies.resolver.policy(category, key, branch=None)`),
cached under the `policy` prefix and forgotten on every write — a read
right after a write always sees the new value, never a stale one.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `policy.view` — every schema key, resolved for `?branch=` (or institution-wide); `?category=` narrows to one category. Each row: `{category, key, value, default, is_default, scope, branch, version, critical, description, updated_at, updated_by_name}` |
| `GET` | `<category>/<key>/` | `policy.view` — one key, same shape; `?branch=`. Unknown category/key is a 404 |
| `PUT` | `<category>/<key>/` | `policy.manage` — `{value, branch?, reason}`; a critical key additionally needs a fresh step-up and `confirm` naming the key exactly, or `400`/`403` `step_up_required`. Validated against the schema (type, range, choices; the `weights` type requires exactly its declared component keys). Writing the value already in force is a no-op: nothing is versioned or audited |
| `DELETE` | `<category>/<key>/` | `policy.manage`; `?branch=`; soft-deletes the row, returning to the schema default (or, for a branch override, falling through to the global row). A critical key needs a fresh step-up. Resetting something never configured is a no-op, not an error |
| `GET` | `<category>/<key>/history/` | `policy.view`; `?branch=` — `PolicyVersion` rows, newest first, paginated: `{id, version, value, changed_by_name, reason, created_at}`. Survives a reset: the version history from before a reset-and-reconfigure is never lost |

`policy.view` is held by superadmin, admin and manager; `policy.manage` by
superadmin and admin only (a deliberate narrowing beyond D-130's usual
"manager and counsellor are equals" — the counsellor does not hold
`policy.view` either, per `docs/erp/PERMISSION_CATALOG.md`). A branch-scoped
caller (`policy.view` at scope `branch`, ADR-02) may only name their own
centre; naming another centre's id is `403`, and a centre that does not
exist is `404` before the scope check runs (rule 2). Every write is audited
(`policy.updated`, `policy.reset`) with the from/to value and the reason.

### Trainer requirements — `/api/v1/requirements/`

A manager's ask of the teaching staff (D-132). Raising one tells every
trainer of the centre — and every manager holding a teaching profile — with a
`requirement.raised` notification linking to `/requirements?open=<id>`.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | `requirement.manage` for the caller's centre (every centre when unbounded), or any trainer for their own centre; a student is refused. Filters `status`, `batch`, `search` |
| `POST` | `` | `requirement.manage` — `title`, `details`, `batch` (through the caller's visible batches), `needed_by` (not in the past); the centre is the batch's, else the caller's |
| `GET` | `<id>/` | as the list; another centre's is a 404 |
| `DELETE` | `<id>/` | `requirement.manage`; `reason` required; reversible from the recycle bin |
| `POST` | `<id>/replies/` | anyone who can see it, while it is `open`; `message`. A trainer's reply tells the raiser, the raiser's tells the trainers who answered |
| `POST` | `<id>/close/` | `requirement.manage`; `fulfilled_by` (a trainer within reach) makes it `fulfilled`, none makes it `closed`; optional `note`. Everyone who answered is told |

Statuses: `open`, `fulfilled`, `closed`. A closed one takes no replies (409).
The three events (`requirement.raised`, `.replied`, `.closed`) are audited and
appear in the activity review under Communication.

Announcements gained the audience `trainers` alongside it: a
`announcement.manage_any` holder addresses the teaching staff of their own
centre without naming each one; a trainer may not address the trainers.

### Exports — every list, in Excel, PDF or CSV

Six list screens are reports too (`students`, `enrollments`, `fee_payments`,
`daily_reports`, `batches`, `activity`), beside the ten analytical ones. All of
them run through `GET /reports/<key>/` and export through
`GET /reports/<key>/export/?as=csv|xlsx|pdf` — `as`, not `format`, because
DRF owns `?format=`. CSV streams at any size; Excel and PDF render inline up
to 2,000 rows and answer 409 past that, at which point the client queues a
background job (`POST /reports/exports/`, now also taking `student`, `since`,
`until`, `actor`, `kind`, `role`) and the requester gets a notification —
`export.ready` or `export.failed` — linking to "Your exports" on the Reports
screen. Filters narrow inside the caller's visible set and never widen it:
`student` resolves through visible students, `activity` needs `audit.view`.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `/api/v1/fees/payments/<id>/receipt/` | staff who can see the enrolment, or the student — the receipt as an A5 PDF; a voided payment renders stamped VOID |

### Fees — `/api/v1/fees/`

A fee belongs to an **enrolment**, not a student: a student on two courses has
two fees, agreed at different times, possibly discounted differently, paid
down on their own timetables. Payments are **ad hoc** — any amount, any past
date, any method — with no instalment schedule; the plan may carry one
optional "next ₹N expected by <date>", which is what gives an expected date
and the overdue flag.

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `enrollments/<id>/` | `fee.view_any`, or the enrolment's own student — the plan with its payments |
| `PUT` | `enrollments/<id>/` | `fee.manage_any` — set or change `agreed_amount`, `discount_amount` (+ `discount_reason`), `notes` |
| `POST` | `enrollments/<id>/next-due/` | `fee.manage_any` — `next_due_amount` + `next_due_on`, both `null` to clear |
| `POST` | `enrollments/<id>/payments/` | `fee.manage_any` — `amount`, `paid_on`, `method` (`cash/upi/card/bank_transfer/cheque/other`), `reference`, `note` |
| `POST` | `payments/<id>/void/` | `fee.manage_any` — `reason` required; the row stays, crossed out |
| `GET` | `enrollments/<id>/history/` | `fee.view_any`, or the student — every audit row for this fee, newest first |
| `GET` | `students/<id>/` | `fee.view_any`, or the student — totals across every course, with the plans |
| `GET` | `me/` | the signed-in student |
| `GET` | `overview/` | `fee.view_any` — collected today/week/month, outstanding, overdue and due-soon lists |

Rules, all enforced in `apps/fees/services.py` regardless of the route in:

- the first payment on a plan is at least ₹1,000 (the registration fee) unless
  the whole fee is smaller; a payment may not exceed the balance or be dated
  ahead; a discount needs a reason and cannot exceed the fee; the fee cannot
  be lowered below what has already been paid;
- `payable`, `paid`, `balance`, `status` (`unpaid/partial/paid/waived`) and
  `is_overdue` are computed server-side; voided payments do not count;
- every payment gets a receipt number (`GRS-R-00001`, a database sequence);
- nothing is deleted — payments are voided, plans are edited with old and new
  values in the audit log (`fee.plan.set`, `fee.plan.updated`,
  `fee.next_due.set`, `fee.payment.recorded`, `fee.payment.voided`);
- the student's coarse `fee_status` is re-derived after every change.

Counsellors and managers hold `fee.manage_any` outright: no approval step.

### Progress — `/api/v1/progress/`

| Method | Path | Access |
| --- | --- | --- |
| `POST` | `lessons/<id>/completion/` | the signed-in student, with a live enrolment |

### Calendar — `/api/v1/calendar/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `` | any signed-in user — only their own events |

Parameters: `?start=` and `?end=` (ISO dates). The window is capped at 120 days;
a wider request is clipped rather than refused.

### Dashboards — `/api/v1/dashboard/`

| Method | Path | Access |
| --- | --- | --- |
| `GET` | `student/` | any signed-in user; returns `is_student: false` for others |
| `GET` | `trainer/` | any signed-in user; returns `is_trainer: false` for others |

---

## Batch and enrolment lifecycles

**Batch**

```
UPCOMING ──► ACTIVE ──► COMPLETED ──► ARCHIVED
    │           │                        ▲
    └───────────┴──► CANCELLED ──────────┘
```

Activating requires an assigned trainer. Cancelling cascades: every live
enrolment is cancelled with it. Completing completes the *active* enrolments
only — a suspended student did not finish the course, and recording that they
did would be a false statement in a record a certificate may be issued from.

**Enrolment**

```
PENDING ──► ACTIVE ⇄ SUSPENDED
   │           │          │
   │           ▼          │
   │       COMPLETED      │
   └───────► CANCELLED ◄──┘
```

`COMPLETED` and `CANCELLED` are terminal. Re-joining means a new enrolment, so
the old record — and the progress attached to it — stays exactly as it was.

---

## Course access

A student reaches non-preview lesson content, resources and video only when all
of the following hold:

1. Their account is active.
2. They hold an enrolment on the course whose status is `active` or `completed`.
3. That enrolment's batch is not cancelled.
4. Today falls inside the enrolment's access window (`start_date` …
   `access_end_date`), where one is set.

Checked live on every request, so suspending an enrolment or cancelling a batch
closes access immediately. Free-preview lessons stay readable to anyone who can
see the course, and staff — administrators and assigned course authors — are not
gated by enrolment at all.

`COURSE_CONTENT_REQUIRES_ENROLMENT` defaults to on. Turning it off is supported
for an open-catalogue or demo deployment.

---

## Schedule conflicts

A class is refused with `409 schedule_conflict` when it would overlap another,
where overlap means **all three** of:

* the same weekday;
* overlapping times, compared in each slot's own time zone — back-to-back
  classes do **not** clash;
* overlapping batch date ranges.

Both a trainer double-booking and a batch double-booking are refused, and the
error names the clashing class. Assigning a trainer to a batch runs the same
check up front, so the refusal arrives at assignment rather than on the next
timetable edit.

---

---

## Capabilities

Authorization is expressed as capabilities, not roles. `GET /api/v1/auth/me/`
returns the caller's list so the interface can decide what to offer; the server
re-checks each one on every request.

| Capability | Admin | Trainer | Student |
| --- | :---: | :---: | :---: |
| `profile.view_own`, `profile.update_own` | ✅ | ✅ | ✅ |
| `user.view_any`, `user.create`, `user.update_any` | ✅ | — | — |
| `user.set_active`, `user.change_role` | ✅ | — | — |
| `student.view_any`, `student.create`, `student.update_any` | ✅ | — | — |
| `student.set_fee_status` | ✅ | — | — |
| `fee.view_any`, `fee.manage_any` (counsellor and manager too) | ✅ | — | — |
| `trainer.view_any` | ✅ | — | — |
| `trainer.create`, `trainer.update_any` (manager too; the one thing a counsellor does not hold) | ✅ | — | — |
| `category.manage` | ✅ | — | — |
| `course.view_any`, `course.create`, `course.update_any` | ✅ | — | — |
| `course.publish_any`, `course.assign_authors` | ✅ | — | — |
| `batch.view_any`, `batch.create`, `batch.update_any` | ✅ | — | — |
| `batch.manage_schedule` | ✅ | — | — |
| `enrolment.view_any`, `enrolment.create`, `enrolment.update_any` | ✅ | — | — |

As with courses, a trainer holds **no** global batch capability. What they see
comes from being the assigned trainer on a batch: their own batches, those
batches' rosters and schedules, and nothing else. A trainer can view what they
teach but cannot edit it, assign themselves, or enrol anybody — all three are
institutional decisions.

A trainer holds **no** global course capability. Everything they may do comes
from a `CourseAssignment` row scoped to a single course:

| Assignment role | May do |
| --- | --- |
| `editor` | Edit the course and its content; submit for review |
| `owner` | The above, plus change the course's status |

---

## Field-level authorization

A user may only change fields their role permits, and an attempt to send any
other field is **rejected with 400** naming the field — never silently ignored.

| Actor | May change on their own record |
| --- | --- |
| Any user | `first_name`, `last_name`, `phone`, profile image |
| Student | address, date of birth, qualification, institution, graduation year, emergency and guardian contacts |
| Trainer | title, bio, skills, expertise, qualifications, years of experience, professional links |

Never self-editable by anyone: `role`, `is_active`, `is_staff`, `is_superuser`,
`email`, `is_email_verified`, `student_id`, `trainer_id`, `fee_status`, `notes`,
`is_accepting_assignments`, and every timestamp.

On a course, never settable through the editor: `code`, `status`,
`published_at`, `content_updated_at`, `created_by`, `updated_by`. On a module or
lesson: `position` and `status` — both have their own endpoints, so neither can
be changed as a side effect of an edit.

---

## Not yet implemented

Attendance, assignments, quizzes, exams, results, certificates, notifications,
reports and analytics have no endpoints. They arrive with the features that
implement them.

Progress exists as a foundation only: a lesson can be marked complete and a
course percentage is derived from it. Watch position, time on task, completion
rules and gated progression are later work — the `LessonProgress` row is shaped
to carry them without reshaping.
