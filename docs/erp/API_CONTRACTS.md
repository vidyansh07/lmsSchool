# API contracts — ERP endpoints

All under `/api/v1/`. Authentication: session cookie + CSRF on writes
(unchanged). Every response uses the existing envelope: success bodies are
plain JSON; errors are `{"error": {"code", "message", "details", "request_id"}}`.
Pagination: `?page=&page_size=` → `{count, page, page_size, total_pages,
next, previous, results}` (existing `DefaultPagination`, max page_size 100).
Every list accepts `?search=` and `?ordering=` where noted. Timeout budget:
15 s statement / 30 s worker; anything longer is a background job.
Idempotency: every POST that creates is safe to retry when it carries a
client key, noted per endpoint. Audit: named per endpoint. Side effects:
named per endpoint. Cache: named where the response is cached.

Common error codes: `validation_error` (400), `authentication_required`
(401), `permission_denied` (403), `step_up_required` (403), `not_found`
(404), `conflict` (409), `throttled` (429).

---

## Authorization (Phase 1–2)

### `GET /roles/`
Permission `role.view`. Lists roles (system first) with `user_count`,
`permission_count`, `is_locked`. Cache: none (small).

### `POST /roles/`
Permission `role.manage`. Body `{slug, name, description, kind, permissions: [{code, scope}]}`.
Validation: slug unique, kind ∈ six; every permission code in the catalog;
every scope ≤ the kind's floor; the resulting set ⊆ the caller's effective
set (ladder). 201 with the role. Audit `role.created`. Side effects: cache
`auth:roles` forgotten on commit.

### `GET /roles/{slug}/` · `PATCH /roles/{slug}/` · `DELETE /roles/{slug}/`
PATCH: name, description, status, permissions (full replacement). System
roles: only description and non-locked grants. DELETE: refused 409 while
`user_count > 0`; system roles refused 403; requires step-up. Audit
`role.updated` with `changes`, `role.deleted`.

### `GET /permissions/`
Permission `role.view`. The catalog with category, description, lockable,
status. Cache 1 h (`auth:permissions`).

### `POST /roles/{slug}/permissions/{code}/lock/` · `.../unlock/`
Permission `permission.lock`, step-up. Audit `permission.locked` /
`permission.unlocked`.

### `GET /roles/matrix/`
Permission `role.view`. `{roles: [...], permissions: [...], cells: {"<slug>": {"<code>": "explicit"|"inherited"|"locked"|"denied"|"system"}}}`.
Cache 10 min (`auth:matrix`), forgotten on any role write.

### `POST /users/{id}/role/`
Existing endpoint extended: body `{role: kind, custom_role?: slug}`.
Refuses a custom role of a different kind (400) or wider than the caller
(403). Audit `user.role_changed`.

### `GET /users/{id}/scope-grants/` · `POST` · `DELETE /users/{id}/scope-grants/{grant_id}/`
Permission `user.update_any` within scope. Body `{batch?|course?}`.

---

## Policies (Phase 3)

### `GET /policies/`
Permission `policy.view`. `?category=` `?branch=`. Returns every key of the
schema with `{category, key, value, default, is_default, scope, branch,
version, critical, updated_at, updated_by}`. Cache 10 min per (branch).

### `PUT /policies/{category}/{key}/`
Permission `policy.manage`. Body `{value, branch?, reason}`; critical keys
additionally require `confirm: "<key>"` and step-up. Validation against the
schema. 200 with the policy. Audit `policy.updated` with from/to. Side
effect: `policy:*` forgotten; auth-related keys take effect on the next
request.

### `GET /policies/{category}/{key}/history/`
Permission `policy.view`. PolicyVersion rows, newest first, paginated.

### `DELETE /policies/{category}/{key}/`
Permission `policy.manage`. Returns to default (soft-deletes the row).

---

## Authentication additions (Phases 4–6)

### `POST /auth/login/` (changed response)
On password success when MFA applies: `200 {"mfa_required": true, "methods": ["totp","email","recovery"], "expires_in": 300}`
and the session holds only `mfa_pending`. Otherwise unchanged.

### `POST /auth/mfa/send-email-code/`
Pending-MFA or authenticated (for step-up/enrol). Throttle `otp`. `204`.
Audit `otp.sent`. Side effect: `Delivery` email (`otp_code`).

### `POST /auth/mfa/verify/`
Body `{method: "totp"|"email"|"recovery", code}`. Completes login (sets
the session) or grants step-up (`purpose` inferred from state). 200 with
the user; 400 `invalid_code` (attempts counted); 429 after limits. Audit
`mfa.verified` / `mfa.failed`. Never logs the code.

### `POST /auth/mfa/totp/enrol/` → `{secret_uri, qr_svg}` (secret held unconfirmed) · `POST /auth/mfa/totp/confirm/` `{code}` → `{recovery_codes: [...]}` (shown once) · `POST /auth/mfa/totp/disable/` (step-up) · `POST /auth/mfa/recovery/regenerate/` (step-up)
All audited; `mfa.enrolled` / `mfa.disabled` also email `security_event`.

### `POST /auth/step-up/`
Body `{password}` or `{method, code}`. Sets `step_up_at`. 204.

### `GET /auth/sessions/` → `[{id, device_label, ip, created_at, last_seen_at, is_current}]` · `DELETE /auth/sessions/{id}/` · `POST /auth/sessions/revoke-others/`
Existing `logout-all/` stays. Audit `session.revoked`.

### `GET /users/{id}/sessions/` · `DELETE /users/{id}/sessions/{sid}/`
Permission `session.view_any` / `session.revoke_any`, step-up on delete.

---

## Forms (Phase 8)

### `GET /forms/` · `POST /forms/` (`form.manage`) · `GET /forms/{slug}/`
Definition with `published_version` and `draft_version` summaries.

### `GET /forms/{slug}/versions/{n}/` · `POST /forms/{slug}/versions/` (new draft from the published one; `cloned_from`) · `PUT /forms/{slug}/versions/{n}/fields/` (full field list; refused 409 if the version is published) · `POST /forms/{slug}/versions/{n}/publish/` (archives the current published; 409 if schema_hash unchanged) · `POST .../unpublish/` · `POST /forms/{slug}/preview/` (validates a sample response, returns errors without storing)
Audit `form.version_created`, `form.published`, `form.unpublished`. Cache
`form:published:<slug>` 1 h, forgotten on publish.

### `GET /forms/published/{slug}/`
Any authenticated user who may create the owning entity. The published
version's fields for rendering (student-visible flags included).

---

## Activities (Phase 9–10)

### `GET /activity-types/` · `POST` · `PATCH /activity-types/{slug}/`
`activity_type.manage` for writes; reads for any staff. Cache
`work:types` 10 min.

### `GET /activities/`
Permission `activity.view_any` (scoped) or assignee/creator. Filters:
`status`, `type`, `category`, `student`, `batch`, `assigned_to`,
`created_by`, `due_before`, `due_after`, `overdue=1`, `mine=1`. Ordering
`due_at`, `-created_at`, `priority`. Each row: summary fields + `student`
(id, name, student_id), `type`, counts. Never the form values (detail only).

### `POST /activities/`
Permission `activity.create` (scoped; trainer: the student must be on a
batch they teach). Body `{student, enrollment?, activity_type, title?,
assigned_to?, planned_at?, due_at?, priority?, student_visible?, client_key?}`.
Validation: creator role allowed by the type; assignee role allowed; assignee
within scope; `client_key` unique per creator for 24 h (idempotent retry
returns the existing 201 body). Pins `form_version`. Audit
`activity.created`. Side effects: notification `activity.assigned`.

### `GET /activities/{id}/`
Detail with `form` (fields of the pinned version), `form_values` (staff:
all; student: visible fields only), `history[]`, `parent`, `children[]`,
`automation_run`.

### `PATCH /activities/{id}/`
Editable while DRAFT/PLANNED/ASSIGNED: title, planned_at, due_at, priority,
assigned_to (activity.assign), student_visible (only to hide).

### `POST /activities/{id}/transition/`
Body `{to, note?}` for `plan`, `assign`, `start`, `cancel`, `reopen`
(reason required for reopen/cancel). 409 on an illegal transition with
`details.allowed: [...]`.

### `POST /activities/{id}/complete/`
Body `{form_values, summary?, duration_minutes?, completed_at?}`. Validates
against the pinned version; derives score/result; moves to COMPLETED or
UNDER_REVIEW. 200 with the detail. Audit `activity.completed`. Side effects
(on commit): `risk.recompute`, `automation.dispatch(ACTIVITY_COMPLETED)`,
notifications. Idempotent: completing an already completed activity is 409.

### `POST /activities/{id}/review/`
Permission `activity.review`, not the performer. Body `{decision:
"approved"|"requires_action", note}`. Audit `activity.reviewed`.

### `DELETE /activities/{id}/`
Permission `activity.delete`; body `{reason}`; soft delete; risk recompute.

### `GET /students/{id}/activities/` — the Student 360 tab (same filters).
### `GET /me/activities/` — the trainer's/counsellor's own work list (`mine=1` sugar).

### `GET /students/{id}/timeline/`
Permission: anyone who can see the student. `?kinds=a,b&since=&until=&cursor=&page_size=`
→ `{results: [{id, occurred_at, kind, title, summary, href, actor: {id, name, role}}], next_cursor}`.
Query budget: ≤ 1 query per registered source + 1 for the student. Tested.

### `GET /students/{id}/360/`
Permission as above. One call: `{profile, enrollment, batch, trainer,
counsellor, progress (from the one calculation), attendance summary,
performance (components + overall), risk (state + triggered), counts:
{activities_open, activities_overdue, assessments, assignments, projects},
fee_status, recent_activities[5], next_actions[5]}`. Cache 1 min per
(student, viewer scope key). Query count asserted flat.

---

## Performance and risk (Phases 12–13)

### `GET /students/{id}/performance/`
Existing shape plus `components: [{key, label, weight, value, contribution,
sources: [...]}]`. Activity sources: `{activity_id, type, score, max_score,
completed_at, performed_by}`.

### `GET /students/{id}/risk/`
`{level, triggered: [{key, label, severity, detail, numbers}], computed_at,
previous_level, changed_at, manual_flag?}`.

### `GET /risk/summary/` — manager dashboard tile source: counts by level within scope, top 20 by severity with links. Cache 1 min.

### `PATCH /policies/risk/…` — thresholds via the policy API (category `risk`); the legacy `performance/risk-thresholds/` endpoint keeps working and writes the same values.

---

## Automation (Phase 14)

### `GET /automations/` · `POST` · `GET /automations/{id}/` · `PATCH` · `DELETE`
`automation.manage`. Validation: trigger known; every condition path in the
trigger's context; every action type known, params match the schema, and
the author holds the action's permission. Audit `automation.created/updated/deleted`.

### `POST /automations/{id}/activate/` (dialog data: `{matched_last_7_days}` from `GET /automations/{id}/preview/`) · `POST .../pause/` · `POST .../test/` `{event_id?}` → `{would_fire, evaluated_conditions[], actions[]}` (dry run, throttle `automation_test`).

### `GET /automations/{id}/runs/` — AutomationRun rows, paginated.

---

## Communication (Phase 19)

### `GET /templates/` · `POST` · `GET /templates/{key}/` · `POST /templates/{key}/versions/` · `PUT /templates/{key}/versions/{n}/` (draft only) · `POST .../approve/` (`template.approve`; WhatsApp: step-up) · `POST .../publish/` · `POST .../preview/` `{variables}` → rendered subject/html/text + `warnings[]` · `POST .../test-send/` (to self only, throttle `communication`)

### `GET /deliveries/`
`communication.view_any` (scoped by recipient's branch). Filters channel,
state, recipient, template, since/until. Never returns OTP bodies.

### `POST /deliveries/{id}/retry/` (`communication.send`, failed only) · `POST /deliveries/{id}/cancel/` (queued only)

### `POST /communication/send/`
`communication.send`. Body `{channel, template, recipients: {students?: [...], batch?, role?}, variables?, confirm_count}`.
Refused 409 if `confirm_count` ≠ the resolved recipient count (the UI shows
the count first). Queues one Delivery per recipient. Audit
`communication.sent` with counts. Throttle `communication`.

### `POST /communication/whatsapp/webhook/` — provider callbacks; token + signature; updates Delivery states; never authenticated by session.

### Announcements (existing, extended)
`POST /announcements/` accepts `audience: "role"|"branch"`, `role`, `branch`, `publish_at`. `POST .../schedule/` moves draft → scheduled; `POST .../cancel/` from scheduled. Beat `announcements.publish_due` every minute.

---

## Search and productivity (Phase 11, 16–18)

### `GET /search/?q=&types=`
Any authenticated user (`search.global`). `q` ≥ 2 chars. Returns
`{groups: [{type, label, results: [{id, title, subtitle, href}], total}]}`
with ≤ 5 per type by default, `types` to expand one. Sources: students,
trainers, users (staff), batches, courses, activities, assessments,
assignments, projects, DSRs — each via its `visible_*`. Throttle `search`.
Audit `search.performed` (counts only). Cache: none.

### `GET /saved-filters/?screen=` · `POST` · `DELETE /saved-filters/{id}/` — per user.

### `GET /dashboards/counsellor/` — `{new_students_today, pending_registrations, follow_ups_due, follow_ups_overdue, unassigned_batch, unassigned_trainer, warnings[]}`; one call; cache 1 min.

### `GET /dashboards/manager/` (existing, extended) — adds `activities: {pending, overdue, under_review}`, `risk: {critical, warning}`, `reviews_due`.

### `GET /dashboards/trainer/` (existing, extended) — adds `today.activities[]` and `work: {pending, overdue}`.

### `GET /dashboards/admin/` (existing, extended) — adds `system: {failed_deliveries, failed_exports, automation_failures, backup: {last_dump_at, last_verified_at}}`.
### `GET /dashboards/counsellor/pipeline/?weeks=12` — `{stages: [{key, label, count}], weekly: [{week, registered, enrolled}]}`. `student.create` (declared, so the authorization matrix sweeps it), scoped through `visible_students`. Stages are a nested chain — each a subset of the one above — computed as `Count(distinct)` annotations over one queryset, not five. Uncached: it takes `weeks`, and a per-caller key without `weeks` would serve the 52-week payload to a 4-week request.
### `GET /fees/collections-trend/?weeks=12` — `[{week, amount, receipts}]`, `amount` a decimal string. `fee.view_any` (declared), scoped through `visible_enrollments`. `Sum` over `FeePayment` with `voided_at IS NULL` — never over `FeePlan`, whose `paid`/`balance`/`status` are Python properties, not columns. Uncached for the same reason as the pipeline, and because a collections chart that does not move after a payment is recorded is a support ticket.

---

## Exports (Phase 20)

### `GET /reports/{key}/count/?filters` → `{rows}` — the preflight for the confirmation dialog; same scoping.
### `GET /reports/{key}/export/?as=csv|xlsx|pdf|print` — `print` returns HTML with a print stylesheet.
### `GET /reports/metrics/enrolment-trend/?weeks=12&batch=&course=` — `[{week, started, active, completed, cancelled}]`. Staff-facing via `access.can_read_reports` (`report.view_any` **or** a trainer profile — a counsellor holds `report.view_any`, so they are a report audience); scope through `access.scope_for` → `metrics._enrollments`, which applies `restrict_to_batches`. `enrolled_at` is a datetime, so `TruncWeek` is pinned to a date or the week boundary drifts with the timezone.
### `GET /reports/metrics/delivery-trend/?weeks=12&batch=&course=` — `[{week, scheduled, held, cancelled, registers_outstanding}]`. Same gate; scope through `metrics._sessions`, the choke point sessions needed because they carry no per-row permission. Bounded at **both** ends — batches are scheduled months ahead. `registers_outstanding` counts only finished, completed classes: a class later today is pending, not outstanding.
### `GET /reports/metrics/dsr-compliance-trend/?weeks=12&batch=&course=` — `[{week, draft, submitted, approved, rejected}]`. Same gate; scope through `metrics._dsr` (default manager, so soft-deleted reports stay out). Submission compliance **only** — deliberately not the DSR's stored attendance counts, which are trainer-editable and would contradict the register-derived `attendance_rate`.
### All three `metrics/*-trend/` routes are declared **above** `reports/urls.py`'s `<slug:key>/` catch-all; below it `ReportView` swallows them and answers for a report key that does not exist. `weeks` is clamped 1..52. None is cached (matching `metrics/` and `attendance-trend/`); an in-body gate is invisible to `test_authorization_matrix.py`, so each has explicit per-role tests in `tests/test_reporting_trends.py`.
### Beat `reporting.expire_exports` nightly: files past `export_retention_days` deleted, jobs marked expired. (Closes a gap the inventory found.)

---

## Attendance history (Phase 22 hardening)

### `GET /attendance/{record_id}/history/` → AttendanceCorrection rows.

---

## Behavioural guarantees (§8–9) that apply to every endpoint above

- GET never mutates. Opening a record, a drawer, a dropdown or a tab issues
  reads only.
- Every mutation is a POST/PATCH/PUT/DELETE behind CSRF, and the UI
  performs it only from an explicit control; dangerous ones behind a
  `ConfirmDialog` with the right `intent`.
- Every list is paginated; every export past the sync limit is a job.
- `X-Request-ID` on every response; the envelope carries it on errors.
- Timeouts: 15 s statement / 20 s browser / 30 s worker; background for more.

## Counsellor's desk (D-140, 7 October 2026)

### Fees
- `PUT /fees/enrollments/<id>/` additionally accepts `installments:
  [{amount, due_on}]` (sent empty = ad hoc) and `installment_count` (the
  default schedule with that many rows; default 6, max 36, 30 days apart,
  first due today). The rows must sum to the fee after discount.
- `PUT /fees/enrollments/<id>/installments/` `{installments: [...]}` —
  `fee.manage_any`; replaces the schedule; audit `fee.installments.set`.
- The plan now carries `installments: [{id, sequence, amount, due_on,
  paid_amount, balance, status: paid|pending|overdue|upcoming}]`, derived.
- `POST /fees/enrollments/<id>/payments/` additionally takes
  `reference_name` (≤120). `method` is still the full enum; the desk offers
  cash, upi, bank_transfer.

### Follow-ups
- `POST /students/<id>/follow-ups/` additionally takes `note` (≤1000 →
  `Activity.summary`); the activity is returned in status `assigned`.

### Enquiries
- `Enquiry.channel: online|offline`, writable through `PATCH`, derived from
  `source` when the source changes and no channel is sent.
- `GET /enquiries/?channel=&source=&follow_up=overdue|today|none&created_after=&created_before=`.
- `GET /enquiries/summary/` → `{stages, channels: {online, offline}, total,
  sources: [{value, label}]}`.
- `GET /dashboards/counsellor/` additionally returns `open_leads_online`,
  `open_leads_offline`, `open_leads_total` (open stages only).

### Attendance
- Register entries carry `mode: offline|online` (saved, or the student's
  default); `POST .../register/` entries accept `mode`. The register carries
  the batch's `delivery_mode`.
- `GET /attendance/present-now/` → `{date, online, offline, total, absent,
  sessions_today, registers_taken}` over `visible_sessions` for today, not
  cancelled; staff only.

---

## The reference-product pass (24 October 2026)

What the ClassPro and Meritto screens needed that did not exist. Every one of
these is covered by its own suite; the reasons live beside the code.

### Courses
- `GET /courses/?active=true|false` — "Show Active" on the catalogue screen
  means *not archived* rather than any one status, filtered on the server so
  a page of twenty is twenty.
- `GET|PUT /courses/<id>/instalments/` — the course's default instalment
  structure: `[{sequence, label, percent, due_after_days}]`. Percentages, not
  rupees, because a plan collects the fee *less that student's discount*. PUT
  replaces the whole structure; the shares must total exactly 100; an empty
  list means "no default structure". Permission: reading needs to see the
  course, writing needs to manage it. Copied into a `FeePlan` the day it is
  created and never read back.
- `DELETE /courses/<id>/` — permission `course.delete` (administrator). 409
  when a batch or an enrolment exists, saying to archive instead.
- `GET|POST /courses/<id>/price/` — unchanged, but now the *only* way a fee
  changes: the course form no longer PATCHes `default_fee`.

### Calendar Pro (activity types)
- `ActivityType` carries `check_conflict`, `reopen_allowed` (default **on**),
  `invite_organiser`, `invite_owner`, `created_by_name`, `updated_by_name`.
- Check conflict refuses a second activity of that type over the same minutes
  for the same assignee (409, naming the booking in the way). The window read
  is a day either side; the longest event allowed is 24 hours.
- `Activity.reminder_minutes_before` overrides its type's: null means "the
  type's", 0 means none at all.
- `POST /activities/` additionally accepts `duration_minutes` and
  `reminder_minutes_before`.

### Communication
- `MessageChannel` gains `sms`. No gateway is configured, so a delivery on it
  **fails** saying so rather than sitting queued; `UNWIRED_CHANNELS` names
  that in one place.
- `MessageTemplate.category: transactional|promotional`, defaulting to
  transactional.
- Email is sent as multipart when the template has an HTML body, with the
  text as the alternative; HTML is sanitised by an email-specific allowlist
  (headings, rules, images, tables; no `style`; `https://` only for `href`
  and `src`; hex-only `bgcolor`).
- Automation action `send_sms`, same shape as `send_whatsapp`.

### Automations
- `GET /automation-rules/?status=&search=`.
- `GET /automation-rules/summary/` → `{total, active, draft, paused}`. Three
  statuses, not the reference product's five: a rule here has no end of life
  to reach.
- Rules carry `created_by_name` / `updated_by_name`.

### The institution's lists
- `POST /academic-years/`, `PATCH /academic-years/<id>/` — `is_current` is
  exclusive and cannot be switched *off* (make another year current instead).
- `POST /banks/`, `PATCH /banks/<id>/`; `POST|PATCH
  /fees/payment-categories/[<id>/]`; `POST|PATCH /fees/tax-groups/[<id>/]`.
  At most one default each, set exclusively. Nothing deletes — `is_active`
  retires a row, and whoever may manage a list sees the retired ones.
  Permission: `settings.manage`. Audit: `settings.list.changed` with what
  changed.

### Batch sheet import
- `POST /batches/import/` (multipart: `file` .xlsx, `dry_run` default
  **true**, optional `branch`). Needs `batch.create` *and* `student.create`.
  Returns `{batches_created, batches_matched, students_created,
  students_matched, enrolments_created, enrolments_existing, batches,
  problems: [{sheet, row, message}]}`. A dry run is the real run inside a
  rolled-back transaction, so the preview is what the import would do. A
  course is matched, never created; a student is matched by email then
  phone; a batch by course, start date and name.

### Comments on a payment or an instalment
- `GET|POST /fees/payments/<id>/comments/` and
  `GET|POST /fees/instalments/<id>/comments/`. Reading needs `fee.view_any`,
  writing `fee.manage_any`. `POST {body}` (≤1000); the response is
  `{id, body, author, created_at}`, and a `GET` returns the thread **oldest
  first**, because a thread reads downwards.
- A comment hangs off exactly one payment or one instalment — the database
  refuses both and refuses neither — and is immutable: there is no `PATCH`
  and no `DELETE`, so the other methods on these two routes are 405.
- `FeePayment` and each instalment row gain `comment_count`, so a table shows
  the size of a thread without a call per row. Both are counted in one
  grouped query per table.
- Internal to the institute. `/fees/me/` does not read comments and neither
  endpoint is reachable by a student, so a desk can record "says he will pay
  after the exam, chasing is pointless" without composing it for the student.
- Audit `fee.comment.added` records the row commented on (target, payment id
  and receipt number, or instalment id and sequence) and the text's *length*
  — never the text, because the audit trail is read far more widely than the
  fee screen is.

### A result held back until somebody releases it
- `ActivityType.release_required` (new). On a type that has it, an activity is
  created with `student_visible = false` **whatever the caller passes** — the
  one flag a caller may not override, because overriding it is the single
  thing it exists to prevent.
- `POST /activities/<id>/release/` `{released: true|false}` — authority is the
  person who performed or was assigned the activity, **or** `activity.review`
  at that centre. Not the `can_review` rule, which refuses the performer:
  reviewing your own work is what that guards against, releasing it is the
  normal case. The second path exists because `performed_by` is `SET_NULL`, so
  a trainer who leaves would otherwise strand the result as "pending" forever.
- Audit `activity.released` records the decision, the type, the student and
  whether a score exists — never the feedback text.
- `release_required` without `visible_to_student` is refused on create and on
  update: it would read as "the student sees this once released" and mean
  nothing, because `student_visible_activities` filters on the type's flag
  first.
- Applied by `work.0011` to the three seeded interview types
  (`mock-interview`, `technical-interview`, `hr-interview`), which were all
  `visible_to_student = true` — so until now a trainer's score and written
  feedback were published the instant they were saved. Activities created
  before the migration are left published: one already read is worse to
  retract than to leave.

### A staff member's record of work
- `GET /users/<id>/record/?start=&end=` → `{person, start, end, counters,
  timeline, timeline_truncated}`.
- **Two ways in, only one a grant:** `staff.view_record` (new, administrator
  and superadmin only, lockable) for anybody else's record, or being the
  person asked about. Ownership is not a capability — somebody who cannot see
  their own admissions count asks a colleague to read it to them. A **manager
  sees nobody's**, including a trainer's (owner's decision, 26 October 2026);
  the trainer oversight a manager already has — reviews, requirements, class
  reports — is unchanged and lives on its own screens.
- `counters` are counted from the domain tables' own attribution
  (`Admission.created_by`, `FeePayment.recorded_by`, `EnquiryNote.author`,
  `Activity.performed_by`, `DSR.trainer`), through the **caller's** visible
  querysets — a count is as much a disclosure as a row. Money uses the
  ledger's `LIVE_PAYMENT`, so a voided or refunded receipt credits nobody;
  otherwise voiding one would be a way to inflate a figure.
- A counter that counts zero is **omitted**, so what a record contains says
  what the job was rather than printing every role's form.
- `timeline` is `AuditLog` by actor, newest first, capped at 200 with
  `timeline_truncated` saying so. It rides the existing
  `audit_actor_time_idx` on `(actor, -created_at)`.
- The window is inclusive at both ends, defaults to the last 30 days, and is
  bounded at 400 days — a longer span is a report, and the export machinery
  answers that.
- This is the engine behind the reports section's "who did what" mode, so
  anything added here appears there without a second implementation.

### A report somebody builds themselves
- `GET /reports/datasets/` → every dataset a report can be built from, with
  its columns, the questions each field will answer (kind + the operators
  that kind allows), and what it will total. **No ORM path appears in this
  response**: a caller asks for `course`, and what the database is asked for
  stays the server's business — which is what stops a field becoming
  reachable by being spelled correctly.
- `POST /reports/build/` `{dataset, columns?, filters?, group_by?, measures?}`
  → `{columns, rows, truncated, grouped}`. A `POST` for a read because the
  request is a structure — filter clauses with a field, an operator and a
  value, some of them lists — and a query string carrying a dozen of those is
  neither readable nor bounded.
- Six datasets to begin with: students, enrolments, fee payments, batches,
  trainers, class reports. Adding a seventh is a dataclass.
- **Refused, by name rather than silently:** a column, filter field,
  operator or measure the dataset does not declare; `in` without a list. A
  filter that quietly matches nothing is indistinguishable from a question
  with no answer, and somebody will read the empty report as fact.
- Rows come from `_queryset_for_user`, the resolver the fixed reports and the
  background exports already share, so every run starts from the caller's own
  visible set and a filter can only subtract from it. **Totals too**: a count
  is as much a disclosure as a row, so grouping runs inside the scoped
  queryset and a group with no visible rows does not appear.
- `truncated` says the answer was cut at 1,000 rows; `grouped` says the rows
  are one per group with totals rather than a list of records. Both are said
  plainly rather than left to be inferred.
- A column may be an expression rather than a field — a person's name is
  three columns in the database and one in a report — declared by the dataset
  so no report has to split a name in two.
