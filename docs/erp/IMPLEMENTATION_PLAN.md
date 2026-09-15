# Implementation plan

Twenty-six phases in dependency order. Each phase lists what it delivers,
its dependencies, the migrations it adds (all additive, ADR-16), the tests
that gate it, the rollback, and its exit criterion. A phase is done when
its checklist rows in `ERP_IMPLEMENTATION_CHECKLIST.md` reach VERIFIED and
the full suites (backend, frontend unit, e2e, crawl) are green on the
branch. Every phase ends with a deploy to staging.

Branch: `feat/erp-platform` (from `feat/erp-foundation`). Each phase is
one or a few commits with the phase number in the subject
(`feat(erp-p01): …`). Fast-forwarded into `feat/erp-foundation` and
deployed at each phase end.

| Phase | Name | Depends on | Delivers | Migrations | Gate tests | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | Planning | — | this package (16 documents) | — | — | — |
| 1 | Dynamic authorization | 0 | `Role`, `Permission`, `RolePermission`; `sync_permissions`; seed of six system roles; cached `has_capability` reading rows; `User.custom_role`; API `/roles/`, `/permissions/`, `/roles/matrix/`; Role Builder and matrix screens; audit actions | accounts 0006–0007 | `test_dynamic_roles`, `test_permission_catalog`, existing 80 modules unchanged, `role-builder` unit tests | `DYNAMIC_ROLES_ENABLED=false` |
| 2 | Scopes and locking | 1 | `RolePermission.scope`, `ScopeGrant`, `scope_for`, every `visible_*` consults it; `is_locked`, lock/unlock endpoints with step-up placeholder (password re-entry until Phase 5); matrix five states | accounts 0008 | `test_scopes` sweep (every list × every scope × two centres), `test_permission_locking` | scope NULL everywhere |
| 3 | Policy management | 1 | `Policy`, `PolicyVersion`, schema registry for 14 categories, `policy()` resolver + cache, API, Policy Builder screen, critical-key confirmation | configuration 0002 | `test_policies` (validation per key, history, cache invalidation) | delete rows → defaults |
| 4 | Email OTP | 3 | `OneTimeCode`, send/verify services, throttles, `otp_code` template, audit | accounts 0009 | `test_otp` incl. concurrency (two verifies) and limits | policy off |
| 5 | MFA | 4 | `MfaDevice`, `RecoveryCode`, pending-MFA login state, enrol/confirm/disable, recovery codes, step-up endpoint and `require_step_up`, security emails, `/settings/security` MFA section, step-up dialog | accounts 0010 | `test_mfa`, `test_step_up`, e2e `auth.spec` MFA path | `mfa.required_roles=[]` |
| 6 | Session management | 5 | `UserSession`, middleware touch, list/revoke endpoints, sessions screen, new-device email, admin revoke | accounts 0011 | `test_sessions` | table advisory |
| 7 | Soft delete | 1 | soft delete on Announcement and every new table as it lands; bin lists new kinds; purge with step-up | announcements 0004 | generic `test_soft_delete` sweep | — |
| 8 | Dynamic forms | 3, 7 | app `forms`: definitions, versions, fields, responses, validator (17 types), API, Form Builder with preview/publish/clone, `student-custom` on the wizard and 360 | forms 0001–0002 (seed) | `test_forms` (each type, immutability, versioning, relation scoping) | archive definitions |
| 9 | Activity engine | 8 | app `work`: `ActivityType`, `Activity`, `ActivityHistory`, transitions, complete/review services, API, seeded catalog (18 types), activity types screen, activity list + drawer, notifications kinds, calendar source, `work.mark_overdue` and `work.reminders` beat | work 0001–0002 (seed), notifications 0004 | `test_work_engine`, `test_work_transitions`, `test_work_visibility`, drawer unit tests, `test_calendar` | disable types |
| 10 | Activity timeline | 9 | `work/timeline.py` sources, `/students/{id}/timeline/`, `/my-activities`, Timeline component | — | `test_timeline` (flat, authz, student filter) | — |
| 11 | Student 360 | 10 | `/students/{id}/360/` endpoint, `/students/[id]` page with tabs, header provenance popover, redirects from the enrolment page, global search endpoint + command palette, server saved filters, unsaved-changes hook | reporting 0003 (SavedFilter) | `test_student_360_flat`, `test_search` per role, `student-360`, `command-palette`, `use-unsaved-changes` unit tests | — |
| 12 | Performance engine | 9 | weighted components with provenance, activity component, policy `performance.weights` (defaults reproduce today), Performance tab, "why" popover, `PerformanceReview` extension | performance 0002 | `test_performance_engine` (equality with today on the fixture; provenance sums), `test_reviews` | weights default |
| 13 | Risk engine | 12 | `RiskState`, `risk.recompute` task with debounce, new rules (activity, project, placement, warning count), policy category `risk`, Risk tab, `/risk/summary/`, `RISK_CHANGED` event, notification kind | performance 0003 | `test_risk_rules`, `test_risk_change_detection`, flat-cost | rules default |
| 14 | Next action automation | 13, 9 | app `automation`: rules, runs, evaluator, actions, dispatch task, seeded rules, Automation Builder with dry-run, activate confirmation | automation 0001–0002 (seed) | `test_automation` (each trigger, each action, idempotency, depth, permission check, loop) | pause all |
| 15 | DSR | 9 | link DSR panel to activities ("create activity from this class"); `dsr.rejected` notification; DSR change history view | — | `test_dsr` extended | — |
| 16 | Trainer workspace | 9, 15 | Today's Work gains the activities panel and drawer; `/teaching/work`; trainer dashboard endpoint extended; trainer work metrics with links | — | `teaching-today`, `teaching-work` unit tests, e2e trainer journey | — |
| 17 | Counsellor workspace | 9, 11 | duplicate detection endpoint + wizard step; follow-up activities; `/dashboards/counsellor/`; dashboard reordered; override with reason | students 0009 (override audit only — no schema) | `test_duplicates`, e2e counsellor journey | — |
| 18 | Manager dashboard and reviews | 12, 13, 14 | manager dashboard extended (activities, risk, reviews due); review form with new fields; trainer Work tab; activity review flow | — | `test_manager_dashboard_flat`, e2e manager journey | — |
| 19 | Communication center | 3, 9 | app `communication`: templates, versions, sanitised renderer, `Delivery`, email channel via outbox, WhatsApp provider abstraction (Null + Meta), webhook, announcements scheduled/cancelled + role/branch audiences, `/admin/communication`, delivery log, manual send with count confirmation, `whatsapp_opt_in` | communication 0001–0002 (seed), announcements 0005, notifications 0005 | `test_templates` (injection), `test_delivery`, `test_whatsapp_provider`, `test_announcements_scheduled`, communication screens unit tests | Null provider |
| 20 | Export system | 11 | count preflight, print format, confirmation dialog with counts everywhere, `reporting.expire_exports`, activity/delivery/automation-run reports | — | `test_export_jobs` extended, `test_export_expiry` | — |
| 21 | Caching | 1–19 | every prefix in PERFORMANCE_PLAN with invalidation; stale-authorization test; dashboard scope keys | — | `test_caching` extended (revocation visible next request) | TTL only |
| 22 | Performance hardening | 21 | flat-cost tests for every new list/dashboard; indexes; load test on the scale dataset; `PERFORMANCE_RESULTS.md`; request dedup/cancel in `useApi`/`useList`; `AttendanceCorrection` history | attendance 0002 | `test_performance` extended; load-test report | — |
| 23 | Backup and recovery | 8, 19 | `backup-media.sh`, `export_configuration`, `--from` restore, cron entries, drill executed and logged | — | `backup.sh --verify`, `backup-media.sh --verify` in CI's e2e job against MinIO | — |
| 24 | Security and regression | all | threat table walked with tests (IDOR sweep on every new endpoint, escalation attempts, stale cache, mass assignment on every serializer, XSS in richtext/templates, CSRF on new POSTs, webhook forgery); bandit/pip-audit/gitleaks clean; `check --deploy` clean; concurrency tests (§78) | — | `test_erp_security_sweep`, `test_concurrency` | — |
| 25 | Production readiness | 24 | `tests/test_erp_journey.py` (the §103 chain), e2e journeys for five roles (§80), crawl for six roles, broken-link test, empty/error state test per screen, RELEASE_READINESS updated with measured figures, FEATURE_STATUS rows, DECISIONS entries, api.md sections, README routes | — | all suites, crawl, e2e release journey | — |

## Phase dependencies (brief §93), restated as checks

- Phases 8+ that render permission-gated screens rely on Phase 1's matrix.
- Phase 9 refuses to start without Phase 8 (`ActivityType.form` is a FK).
- Phases 10, 12, 14, 16, 18 refuse to start without Phase 9.
- Phase 18 refuses to start without Phase 12.
- Phase 14's `send_*` actions are `skipped` with reason until Phase 19
  publishes templates; the engine ships in 14, the channels in 19.
- Phase 20 uses the scoped querysets and can proceed in parallel with 12–19.

## Migration plan

- Every migration additive; fresh install and reverse proven by
  `scripts/check_migrations.sh` at each phase end; the drift job in CI.
- Seed migrations (system roles, permissions, forms, activity types,
  automations, templates) are `RunPython` with a reverse that deletes only
  `is_system=True` rows nobody references (PROTECT otherwise).
- Data migrations that backfill (none planned) would follow the
  three-release pattern.
- Upgrade test: restore the staging dump into a scratch database and
  migrate forward at each phase end (`backup.sh --verify` then `migrate`).

## Rollback plan per phase

Every feature has a kill switch or a data-level rollback in the table
above; none requires a schema reversal. A failed deploy reverts by
checking out the previous commit and redeploying; migrations from the
failed phase stay applied (additive, harmless).

## Testing plan per phase

Backend: unit (services), API (views with `api_client_no_csrf`),
authorization (the sweep pattern in `test_branch_scoping_api.py`),
flat-cost, concurrency (threads + `transaction.atomic` savepoints for the
§78 cases), migration (`check_migrations.sh`). Frontend: unit per screen
(six states), `capability-mirror`, `theme-contrast`; e2e per journey;
crawl per role before every deploy. Security: bandit, pip-audit, npm
audit, gitleaks, `check --deploy` (CI, existing).

## Documentation per phase

`docs/api.md` section, `docs/FEATURE_STATUS.md` row(s), `docs/DECISIONS.md`
entry when a product call was made, `README.md` route table, this
package's checklist statuses.

## Order of work inside a phase

Model + migration → service + tests → API + tests → frontend lib + types →
screen + six-state tests → navigation → docs → crawl → deploy.
