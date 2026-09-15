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

---

## Exports (Phase 20)

### `GET /reports/{key}/count/?filters` → `{rows}` — the preflight for the confirmation dialog; same scoping.
### `GET /reports/{key}/export/?as=csv|xlsx|pdf|print` — `print` returns HTML with a print stylesheet.
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
