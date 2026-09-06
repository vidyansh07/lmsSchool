# Feature status

The working task board. One row per feature. A row is `DONE` only when it is
tested and verified running — not when the code exists.

**Statuses:** `TODO` · `IN_PROGRESS` · `BLOCKED` · `DONE`

Totals at last full run: **1,415 backend** · **80 frontend unit** ·
**82 end-to-end** = 1,577 tests, all passing.

---

## Phase 0–3 — delivered

| Feature | Phase | Status | Main files | Tests | Security checks | Manual verification | Known limitation | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Project foundation, environments, CI | 0 | DONE | `config/settings/*`, `.github/workflows/ci.yml` | `test_smoke`, `test_security_config` | `check --deploy` clean; env guards | Stack runs via compose | CI never executed on GitHub (no remote) | 2026-09-01 |
| Health probes | 0 | DONE | `apps/health/` | `test_health` | No config exposed | `/health/ready/` live | — | 2026-09-01 |
| Error envelope, audit foundation | 0 | DONE | `apps/common/exceptions.py`, `apps/audit/` | `test_errors`, `test_audit` | No traces leaked; secrets scrubbed | Live 4xx/5xx bodies | — | 2026-09-01 |
| Authentication (login/logout/reset/verify/sessions) | 1 | DONE | `apps/accounts/` | `test_auth`, `test_password_flows`, `test_email_verification` | Enumeration, CSRF, rate limits | Full flow via curl | No real SMTP credentials supplied | 2026-09-01 |
| Roles and capability matrix | 1 | DONE | `apps/accounts/roles.py`, `apps/common/permissions.py` | `test_security_access_control` | Fail-closed asserted | Per-role live checks | — | 2026-09-01 |
| User / student / trainer management | 1 | DONE | `apps/students/`, `apps/trainers/` | `test_user_admin`, `test_students_api`, `test_trainers_api` | IDOR, mass assignment | Live admin CRUD | — | 2026-09-01 |
| Profile image upload | 1 | DONE | `apps/common/uploads.py` | `test_profile_image_upload` | Content verified, EXIF stripped | PHP-as-PNG refused live | Local volume, not S3 | 2026-09-01 |
| Course catalogue and authoring | 2 | DONE | `apps/courses/` | `test_courses_api` | Draft invisibility | Live admin + trainer | — | 2026-09-01 |
| Modules, lessons, ordering, publishing | 2 | DONE | `apps/courses/services.py` | `test_courses_api` | Mass assignment | Live reorder | — | 2026-09-01 |
| Lesson resources | 2 | DONE | `apps/courses/`, `apps/common/uploads.py` | `test_course_resources` | Extension+magic pairing, traversal | Live upload/download | Local volume, not S3 | 2026-09-01 |
| Course access control | 2/3 | DONE | `apps/courses/access.py` | `test_courses_security`, `test_course_access_by_enrollment` | Unpublished invisible; enrolment gate | 200 enrolled / 403 not | — | 2026-09-01 |
| Batches and schedules | 3 | DONE | `apps/batches/` | `test_batches_api`, `test_schedule_conflicts` | Trainer scoping | Live CRUD | — | 2026-09-01 |
| Schedule conflict detection | 3 | DONE | `apps/batches/conflicts.py` | `test_schedule_conflicts` | Backend-enforced | Seeder proves refusal | — | 2026-09-01 |
| Enrolment | 3 | DONE | `apps/enrollments/` | `test_enrollments_api`, `test_enrollment_security` | Capacity race, duplicates, IDOR | Live §16 attack list | — | 2026-09-01 |
| Calendar | 3 | DONE | `apps/dashboards/calendar.py` | `test_dashboards_calendar` | Per-source access control | Live student calendar | — | 2026-09-01 |
| Student + trainer dashboards | 3 | DONE | `apps/dashboards/views.py` | `test_dashboards_calendar` | Query ceilings asserted | Live both roles | — | 2026-09-01 |
| Lesson progress foundation | 3 | DONE | `apps/enrollments/models.py` | `test_dashboards_calendar` | Owner-only | Live completion toggle | Minimal by design | 2026-09-01 |

---

## Phase 4 — academic operations

| Feature | Phase | Status | Main files | Tests | Security checks | Manual verification | Known limitation | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4.0 SUPERADMIN + MANAGER roles | 4 | DONE | `apps/accounts/roles.py` | `test_security_access_control` (8 new) | Ladder monotonic; platform config superadmin-only; manager cannot change accounts | Manager and superadmin reach the right endpoints | — | 2026-09-01 |
| 4.1 Class sessions | 4 | DONE | `apps/sessions/` (models, services, access, views) | `test_class_sessions` (23) | Trainer cannot touch an unrelated batch's class; students read-only | Generation idempotent; reschedule keeps the original | Frontend not yet built | 2026-09-01 |
| 4.1a Trainer assignment history | 4 | DONE | `apps/sessions/models.py`, `apps/batches/services.py` | `test_class_sessions` | Students cannot read staffing history | Opening stint recorded at batch creation | — | 2026-09-01 |
| 4.2 Daily attendance | 4 | DONE | `apps/attendance/` | `test_attendance` (21) | Trainer scope, student isolation, no marker identity leaked | Bulk marking, corrections, percentages | Frontend not yet built; no admin on/off switch yet (4.7) | 2026-09-01 |
| 4.3 Assignment system | 4 | DONE | `apps/assignments/` (models, access, services, views) | `test_assignments` (36) | Trainer scope, student isolation, server-side mark bound, strict fields | Create, publish, submit, grade, return, resubmit | Frontend not yet built; per-assignment passing mark until 4.7 | 2026-09-01 |
| 4.4 Assignment file security | 4 | DONE | `apps/common/uploads.py`, `assignments/views.py` | `test_assignment_files` (31) | Allowlist, magic-byte pairing, inert `.bin` storage, octet-stream attachment, nosniff, sandbox CSP, download authorization | Code, PDF, forged PDF, executables, traversal names, classmate download | Local filesystem storage; S3 not wired (no credentials) | 2026-09-01 |
| 4.5 Weekly tests / external assessments | 4 | DONE | `apps/assessments/` (models, access, services, views) | `test_assessments` (23) | Trainer scope, student isolation, https-only links, server-side mark bound | Schedule, publish, mark, absent, file-backed test graded through the assignment path | Native quiz engine is Phase 5 | 2026-09-01 |
| 4.6 Trainer result import | 4 | DONE | `apps/assessments/importers.py`, `views.ResultImport*` | `test_result_import` (26) | Type/size/row bounds, formula-cell refusal, unknown-student and duplicate detection, all-or-nothing transaction, import audit record | CSV and XLSX preview then confirm; cohort change between the two rolls back | Import runs inline, not queued (no worker yet) | 2026-09-01 |
| 4.7 Academic configuration | 4 | DONE | `apps/academics/` (models, policies, services, views) | `test_academic_config` (20) | `academic.configure` is admin-only; reading is open; unknown rules rejected | Changing the passing % flips a stored mark's verdict with no deployment | Per-course overrides only, not per-batch (D-032) | 2026-09-01 |
| 4.8 Phase 4 frontend | 4 | DONE | `frontend/app/teaching/*`, `app/my-*`, `app/admin/academics` | `playwright e2e/academics.spec.ts` (5) | UI hides what a role cannot use; every control re-checked by the backend | All ten screens loaded in a browser against the seeded stack | No offline/PWA support | 2026-09-01 |
| 4.8 Phase 4 end-to-end journeys | 4 | DONE | `frontend/e2e/academics.spec.ts` | 3 named journeys + 2 refusal cases | Executable upload refused in the browser; unknown student blocks an import | Register → student sees it; set → submit → grade → student sees grade; import preview → confirm → student sees result | — | 2026-09-01 |
| 4.x Role-grant containment (security fix) | 4 | DONE | `apps/accounts/roles.py::can_grant_role` | `test_security_access_control` (6 new) | An admin cannot mint a superadmin; refusals are audited | Verified through the users API | — | 2026-09-01 |
| 4.x Academic demo seed | 4 | DONE | `apps/assessments/management/commands/seed_academics.py` | `test_seed_academics` (10) | Refuses to run where demo data is not allowed | `make seed-academics`; converges on repeat runs | — | 2026-09-01 |
| 5.1 Project system | 5 | DONE | `apps/projects/` (models, access, services, views) | `test_projects` (38) | Trainer scope, student isolation, server-summed rubric, transition table | Set, publish, assign, hand in, rework, approve | Team projects not built (field reserved, D-034) | 2026-09-01 |
| 5.2 Multiple project rules | 5 | DONE | `services.required_project_progress` | `test_projects` | Students read only their own progress | Required vs optional; outstanding list surfaced | Read by Phase 6 completion | 2026-09-01 |
| 5.3 Project file security | 5 | DONE | `apps/projects/models.py`, `views.ProjectFileView` | `test_projects` (4 file tests) | Same pipeline as §4.4: allowlist, magic bytes, inert `.bin`, octet-stream attachment, sandbox CSP | Executable refused; traversal name neutralised; classmate 404 | Local filesystem storage; S3 not wired | 2026-09-01 |
| 5.4 Native question bank | 5 | DONE | `apps/questions/` | `test_question_bank` (19) | Students get an empty queryset — the bank holds the answers; broken option sets refused | MCQ, multiple, true/false, short, long, file | Bulk import not built | 2026-09-01 |
| 5.5 Final examination engine | 5 | DONE | `apps/exams/` | `test_exams` (35) | Frozen paper, server clock, server-computed score, system RNG, no answer fields in the candidate serializer | Draw, auto-save, submit, auto+manual marking, release | Expiry is lazy, not swept (D-038) | 2026-09-01 |
| 5.6 Exam failure handling | 5 | DONE | `apps/exams/services.py` | `test_exams` (11 failure cases) | Refresh, browser close, duplicate submit, expiry, timer tampering, attempt limit, unauthorized access, cross-student access, concurrent start | All nine reproduced as tests | — | 2026-09-01 |
| 5.7 Phase 5 frontend | 5 | DONE | `frontend/app/teaching/{projects,exams,questions}`, `app/my-projects`, `app/exams`, `app/attempts` | `playwright e2e/projects-exams.spec.ts` (4) | Review controls only on handed-in work; candidate never sees an answer | All seven screens driven in a browser | — | 2026-09-01 |
| 5.7 Phase 5 end-to-end journeys | 5 | DONE | `frontend/e2e/projects-exams.spec.ts` | 2 named journeys + 2 refusal cases | Executable deliverable refused; another candidate's attempt 404s | Set → hand in → review → feedback; create exam → sit → auto-save → submit → release → result | Suite is repeatable: runs back to back green | 2026-09-01 |
| 5.x Concurrent exam start (bug fix) | 5 | DONE | `apps/exams/services.py::start_attempt` | `test_exams` threaded test | Two simultaneous starts return one attempt | Found by the E2E run, not by review | — | 2026-09-01 |
| 5.x Local Redis cache | 5 | DONE | `docker-compose.yml`, `requirements/base.txt`, `Makefile` | `test_health` | Rate-limit counters now shared across workers | Cache roundtrip verified in Redis; readiness `ok` | Not yet a Celery broker | 2026-09-01 |
| 6.1 Lesson progress | 6 | DONE | `apps/enrollments/models.py`, `apps/progress/reports.py` | `test_progress_completion` | Enrolment isolation | Draft lessons excluded; counts match modules | Video resume deliberately not built (§6.1) | 2026-09-01 |
| 6.2 Module progress | 6 | DONE | `apps/progress/reports.py::module_progress` | `test_progress_completion` | — | One grouped query, not one per module | — | 2026-09-01 |
| 6.3 One course progress calculation | 6 | DONE | `apps/progress/reports.py::progress_report` | `test_progress_completion` (35) | Students read only their own | Every screen reads it; none computes its own | — | 2026-09-01 |
| 6.4 Configurable completion rules | 6 | DONE | `apps/progress/rules.py`, `apps/academics/models.py` | `test_progress_completion` | Rules are admin-configurable only | All seven conditions; off-rules still reported; threshold change takes effect at once | — | 2026-09-01 |
| 6.5 Online + offline students | 6 | DONE | `apps/batches/models.py::DeliveryMode`, `Enrollment.effective_delivery_mode` | `test_progress_completion` | — | One architecture; per-student override | Nothing branches on mode beyond configuration | 2026-09-01 |
| 6.6 Completion workflow | 6 | DONE | `apps/progress/` (models, services, views) | `test_progress_completion` | `completion.approve` is admin-only; trainers and students refused | Eligible → approve → enrolment completes; override recorded as one | — | 2026-09-01 |
| 6.7 Certificates | 6 | DONE | `apps/certificates/` | `test_certificates` (28) | Approval required before issue; snapshot frozen; one live certificate per completion | Issue, reissue, revoke, PDF with QR | PDFs rendered on demand, not stored | 2026-09-01 |
| 6.8 Public verification | 6 | DONE | `certificates/views.py::VerifyCertificateView` | `test_certificates` | Unguessable 160-bit code, throttled, allowlist response, revoked still verifies | Checked signed-out in a browser | — | 2026-09-01 |
| 6.9 Phase 6 frontend and E2E | 6 | DONE | `frontend/app/my-progress`, `app/admin/{completions,certificates}`, `app/verify/[code]` | `playwright e2e/completion-certificates.spec.ts` (5) | Public page leaks no email, student id or batch code | Approve → issue → download → verify, then revoked as teardown | — | 2026-09-01 |
| 6.x E2E repeatability | 6 | DONE | `frontend/e2e/*.spec.ts` | full suite twice, back to back | — | Journeys derive their batch from the student's own enrolments and restore what they consume | — | 2026-09-01 |
| 7.1 Notifications | 7 | DONE | `apps/notifications/` | `test_notifications` (25) | Scoped to the recipient; a deactivated account is never notified | Eight event kinds wired to real events | In-app and email only; no push (D-049) | 2026-09-01 |
| 7.2 Email service layer | 7 | DONE | `notifications/channels.py`, `templates.py`, `send_pending_email` | `test_notifications` | Failures scrubbed of secrets before storing or logging | Send, fail, retry, give up | Retry is a cron command, not a worker (D-052) | 2026-09-01 |
| 7.3 Announcements | 7 | DONE | `apps/announcements/` | `test_notifications` | Trainers limited to their own batches; students never see a draft | Draft → publish → cohort notified | — | 2026-09-01 |
| 7.4 Unified calendar | 7 | DONE | `apps/dashboards/calendar.py` (4 new sources) | `test_learning_and_discussions` | Each source resolves its own access | Classes, assignments, tests, exams, projects in one feed | — | 2026-09-01 |
| 7.5 Student learning experience | 7 | DONE | `apps/learning/` | `test_learning_and_discussions` (22) | Bookmarks and notes are private; no staff view | Continue learning, recent, history, upcoming | — | 2026-09-01 |
| 7.6 Discussions | 7 | DONE | `apps/discussions/` | `test_learning_and_discussions` | Batch-scoped; moderation is trainer-or-capability; hidden replies stay visible to their author | Ask, answer, pin, close, hide | — | 2026-09-01 |
| 7.7 Batch directory | 7 | DONE | `learning/views.py::BatchDirectoryView` | `test_learning_and_discussions` | Names and student ids only; switchable off | Verified no contact data reaches the page | — | 2026-09-01 |
| 7.8 Gamification | 7 | NOT BUILT | — | — | — | — | Deliberate: bookmarks and notes built, badges and points declined (D-057) | 2026-09-01 |
| 7.9 Phase 7 frontend and E2E | 7 | DONE | `frontend/app/{notifications,announcements,discussions,my-learning}` | `playwright e2e/communication.spec.ts` (7) | Draft invisible to students; no email address on any student-facing page | Announce → notified; ask → answered → closed | — | 2026-09-01 |
| 7.x Project list N+1 (bug fix) | 7 | DONE | `projects/views.py`, `services.ensure_student_projects` | `test_projects` query-count test | — | The page made one request per project and got slower every run | — | 2026-09-01 |
| 8.1 Configuration centre | 8 | DONE | `apps/academics/` (grade bands, academic calendar) | `test_reporting`, `test_academic_config` | `academic.configure` only; bands validated | Bands change grades in reports at once; holidays skip class generation | Email templates stay in code (D-051) | 2026-09-01 |
| 8.2 Trainer configuration | 8 | DONE | `apps/batches/`, `apps/courses/` (existing), `reports/trainer_activity` | `test_reporting` | Trainers stay scoped to their batches everywhere | Assignment, reassignment and authoring already existed; activity now reportable | — | 2026-09-01 |
| 8.3 Reports | 8 | DONE | `apps/reporting/reports.py` (10 reports) | `test_reporting` (60) | Built from a scoped queryset; a filter cannot widen access | Every report run and exported against real rows | — | 2026-09-01 |
| 8.4 Dashboards | 8 | DONE | `apps/reporting/dashboards.py` | `test_reporting` query-count tests | Admin dashboard is capability-gated | Bounded queries; batch summaries in one grouped query | — | 2026-09-01 |
| 8.5 Bulk import/export | 8 | DONE | `apps/reporting/importers.py`, `exports.py` | `test_reporting` | Preview→confirm, all-or-nothing, formula neutralisation, separate export capability | Students and attendance; CSV streamed | XLSX export not built — CSV only | 2026-09-01 |
| 8.6 Analytics | 8 | DONE | `apps/reporting/metrics.py` | `test_reporting` | Scope enforced inside the metric helper | Nine metrics, each with a documented definition; attendance trend by week | — | 2026-09-01 |
| 8.7 Phase 8 frontend and E2E | 8 | DONE | `frontend/app/admin/{overview,reports,imports}` | `playwright e2e/reporting.spec.ts` (7) | Student sees no reports; trainer reads but cannot export | Overview, run report, export CSV, import preview → confirm | — | 2026-09-01 |
| 8.x Readiness probe race (bug fix) | 8 | DONE | `apps/health/checks.py` | `test_health` threaded test | Concurrent probes no longer fail each other | Found by a full E2E run reporting a false 503 | — | 2026-09-01 |
| 9.1 Authentication hardening | 9 | DONE | `apps/accounts/` (unchanged), `tests/test_auth.py` | `test_auth` (17) | Throttled, generic errors, hashed tokens, secure cookies | Sign-out-everywhere ends a second browser; an expired session is refused | No MFA (documented) | 2026-09-01 |
| 9.2 Authorization matrix | 9 | DONE | `tests/test_authorization_matrix.py` | 160 tests | Every route swept per role; object-level cross-tenant checks | A student typing an admin URL gets nothing back | — | 2026-09-01 |
| 9.3 Private file storage | 9 | DONE | `apps/common/storage.py`, `config/settings/` | `test_file_storage_security` (21) | Private ACL, signed expiring URLs, boot guard against a public bucket | Real round trip against a mocked S3 bucket | No bucket provisioned — credentials are a human step | 2026-09-01 |
| 9.3a Malware scan hook | 9 | DONE | `apps/common/scanning.py` | `test_file_storage_security` | Fails closed; refusal never names the detection; audited | Rejection path exercised by a test scanner | No scanner configured | 2026-09-01 |
| 9.4 API security | 9 | DONE | `apps/common/throttling.py`, `apps/reporting/views.py` | `test_data_and_audit_security`, `e2e/hardening.spec.ts` | Exports and imports carry their own rate limit; headers verified in the browser | Headers and cookie flags checked against the running stack | — | 2026-09-01 |
| 9.5 Data minimisation | 9 | DONE | serializers (unchanged), `tests/test_data_and_audit_security.py` | 31 tests | Rosters, registers and the directory carry no contact or fee data | Asserted per field on live responses | — | 2026-09-01 |
| 9.6 Audit completeness | 9 | DONE | `apps/common/exceptions.py`, `apps/audit/` | `test_data_and_audit_security` | Every 403 recorded, deduplicated against view-level entries | Every category in §14.6 asserted present | — | 2026-09-01 |
| 9.7 Dependency security | 9 | DONE | `.github/workflows/ci.yml`, `docs/security.md` §16 | CI gates | pip-audit, npm audit, bandit, gitleaks all clean | Run locally and in CI | CI has never executed — no git remote | 2026-09-01 |
| 9.8 Database security | 9 | DONE | `infra/db/least-privilege.sql`, `tests/test_database_security.py` | 21 tests | Two roles, no DDL for the app, append-only audit log | Grants applied to a scratch database and verified | Roles are a deployment step | 2026-09-01 |
| 9.9 Performance at scale | 9 | DONE | `apps/progress/bulk.py`, `apps/reporting/`, `seed_scale_data` | `tests/test_performance.py` (27) | Reports stay scoped while going flat | 400 students / 16k attendance / 3.2k results; every report profiled | Scale data needs its own database | 2026-09-01 |
| 9.9a N+1 and slow-query fixes | 9 | DONE | reports, dashboards, `Enrollment.with_related` | `test_performance` growth tests | — | student_progress 7,400→42 queries; batch dashboard 4,097→18 ms; enrolment list 34→9 queries | — | 2026-09-01 |
| 9.10 Background work | 9 | DONE | `config/celery.py`, `apps/notifications/tasks.py`, compose worker+beat | `tests/test_background_work.py` (14) | No result backend; eager mode refused in deployment; credential mail never queued | Real worker consumed real tasks; beat fired the sweep on schedule | Redis is local — no managed broker | 2026-09-01 |
| 9.11 Integration boundaries | 9 | DONE | `apps/assessments/models.py`, settings | `test_data_and_audit_security` | External tests are an https link only; no gateway; credentials from env | Asserted no token/credential field exists | — | 2026-09-01 |
| 9.x Deterministic pagination (bug fix) | 9 | DONE | `apps/common/pagination.py` | `test_performance` paging tests | A row can no longer appear on two pages or none | Paged through tied rows and through a nullable sort column | — | 2026-09-01 |
| 9.x Archive a brief (UI gap) | 9 | DONE | `app/teaching/{assignments,projects}/[id]/page.tsx` | `e2e/academics.spec.ts`, `e2e/projects-exams.spec.ts` | Same capability as publish/close | Trainer archives; the student's list drops it; handed-in work is kept | — | 2026-09-01 |
| 10.1 Final regression | 10 | DONE | whole suite | 1,221 + 61 + 69 | Every gate clean | Suite green on the dev stack; journey green on clean staging | 7 specs fail on staging (see RELEASE_READINESS) | 2026-09-02 |
| 10.2 Mandatory journey | 10 | DONE | `frontend/e2e/release-journey.spec.ts` | 1 journey, 23 steps | Ends signed out, verifying publicly | Repeated passes on a rebuilt-from-empty staging | Learns as a seeded student (D-086) | 2026-09-02 |
| 10.3 Verification script | 10 | DONE | `scripts/verify_demo.sh` | 19 checks | Refuses an environment holding a non-reserved address | Run against local and staging, both clean | — | 2026-09-02 |
| 10.4 Staging environment | 10 | DONE | `docker-compose.staging.yml`, `infra/proxy/` | `verify_demo.sh staging` | DEBUG off, hardened settings, TLS, secure cookies | Full stack up, seeded, E2E run against it | Self-signed certificate; MinIO not AWS | 2026-09-02 |
| 10.5 Staging seed dataset | 10 | DONE | `seed_demo_data`, `seed_academics` | `test_seed_*` (16) | Fake data only, reserved domains | Every §15.5 item present, with edge cases | — | 2026-09-02 |
| 10.6 Migration safety | 10 | DONE | `scripts/check_migrations.sh`, `docs/operations.md` | 4 checks | No destructive operation in 58 migrations | Fresh install, reverse and re-apply, all clean | — | 2026-09-02 |
| 10.7 Backup and restore | 10 | DONE | `scripts/backup.sh`, `docs/operations.md` | `--verify` | Backups are git-ignored | Dump restored into a scratch database, sequences checked | Object storage not backed up — no bucket | 2026-09-02 |
| 10.8 Production configuration | 10 | DONE | `.env.production.example`, `infra/docker/` | `check --deploy` | gunicorn, never runserver; no secret in the template | Both deploy checks clean | Never deployed | 2026-09-02 |
| 10.9 Final security gates | 10 | DONE | `make security`, `make secrets` | all | bandit, pip-audit, npm audit, gitleaks, deploy checks | All clean; the ignore guard proven to fail | CI has never run | 2026-09-02 |
| 10.10 Release report | 10 | DONE | `docs/RELEASE_READINESS.md` | — | States plainly it is not production ready | Five human tasks listed | — | 2026-09-02 |
| 10.x CSP blocked hydration (bug fix) | 10 | DONE | `frontend/middleware.ts`, `app/layout.tsx` | `verify_demo.sh` nonce check, E2E on staging | Nonce per request, no `unsafe-inline` | The production build works in a browser | — | 2026-09-02 |
| 10.x Stale CSRF after sign-out (bug fix) | 10 | DONE | `frontend/lib/api.ts` | `tests/unit/api.test.ts` (2) | Only `csrf_failed` retried, once | Sign out, sign in, act — no longer fails first | — | 2026-09-02 |
| 10.x Generate classes (UI gap) | 10 | DONE | `app/admin/batches/[batchId]/page.tsx` | release journey | Same capability as the API | A timetable becomes classes from the screen | — | 2026-09-02 |
| 10.x Mark a lesson complete (UI gap) | 10 | DONE | `app/courses/[slug]/learn/[lessonId]/page.tsx` | release journey | Students only, via their enrolment | A student can finish a lesson | — | 2026-09-02 |
| 11.1 Role hierarchy | 11 | DONE | `apps/accounts/roles.py`, `services.py` | `test_role_hierarchy` (50) | Authority downward only; refusals audited with both roles | Every ordered pair of roles checked | Superadmins may administer each other, by design (D-096) | 2026-09-02 |
| 11.2 User administration | 11 | DONE | `app/admin/users/[userId]/`, `user_views.py` | `test_role_hierarchy`, `e2e/role-administration.spec.ts` (6) | Email change unverifies and ends sessions; links not passwords | Superadmin configures an admin end to end in a browser | Verification cannot be granted by hand (D-100) | 2026-09-02 |
| 11.3 Superadmin holds every power | 11 | DONE | `roles.py`, route sweep | `test_authorization_matrix` | No route refuses a superadmin | Whole resolver swept | Two self-service `/me/` routes excepted, named | 2026-09-02 |
| 11.4 Light theme | 11 | DONE | `app/globals.css` | `tests/unit/theme-contrast.test.ts` (14) | Every pair meets WCAG AA, measured not estimated | Dark-OS viewer still sees light | No dark mode, by request | 2026-09-02 |
| 11.5 Sidebar navigation | 11 | DONE | `components/app-shell.tsx`, `navigation.ts` | `e2e/interface.spec.ts` (7) | Links filtered by capability; server still enforces | Keyboard reachable, focus visible, closes on navigation | Students keep the top bar, by design | 2026-09-02 |
| 11.6 Interface quality | 11 | DONE | shell, cards, fields | `interface.spec.ts` | — | One current-page marker; grouped navigation; stale footer removed | — | 2026-09-02 |
| 11.x Deferred audits leaked between tests (bug fix) | 11 | DONE | `tests/conftest.py` | whole suite | — | A queued entry no longer surfaces in a later test | — | 2026-09-02 |
| 10.x Cancelled batch on today's list (bug fix) | 10 | DONE | `apps/sessions/views.py` | `test_class_sessions` (2) | A cancelled batch is not teaching today | Its class disappears; history kept | — | 2026-09-02 |
| 10.x Seeder died on a batch with no timetable (bug fix) | 10 | DONE | `seed_academics.py` | `test_seed_academics` | Skipped and reported, not fatal | Seed completes with timetables stripped | — | 2026-09-02 |
| 10.x One shared E2E sign-in helper | 10 | DONE | `frontend/e2e/helpers.ts` | whole suite | Waits out the credential throttle rather than raising it | 45→61 staging passes | Seven specs still dev-specific | 2026-09-02 |

## Phases 5–10 — not started

| Phase | Scope | Status |
| --- | --- | --- |
| 5 | Projects, question bank, final exams | TODO |
| 6 | Progress, completion rules, certificates | TODO |
| 7 | Notifications, email, announcements, discussions | TODO |
| 8 | Admin control centre, reports, analytics, bulk data | TODO |
| 9 | Security, performance, reliability hardening | TODO |
| 10 | Release engineering, staging, verification script | TODO |

---

## Phase 12 — ERP foundation

Built on the audited baseline in `PROJECT_IMPLEMENTATION_REPORT.md`. The eight
gaps that report names are being closed in order; this table grows a row per
phase.

| Feature | Phase | Status | Main files | Tests | Security checks | Manual verification | Known limitation | Last verified |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12.1 COUNSELLOR role | 12 | DONE | `apps/accounts/roles.py`, `migrations/0004_alter_user_role.py` | `test_counsellor_rbac` (63), `test_role_hierarchy` (62; 36 authority pairs + a completeness guard), `test_authorization_matrix` | Ladder containment asserted; the role holds nothing academic and no `user.*`; both authority gates tested together | Registered a student, opened and staffed a batch, enrolled — all through the API as a counsellor | No counsellor screens yet; the workflow UI is Phase 5 of the plan | 2026-09-06 |
| 12.2 DSR, performance and export capabilities | 12 | DONE | `apps/accounts/roles.py` | `test_counsellor_rbac`, `test_authorization_matrix` | Declared before use, so the phases that consume them cannot invent their own check | Present in the capability matrix and the generated schema | Nothing consumes them yet — deliberate, they land with their features | 2026-09-06 |
| 12.3 Report export requires read access | 12 | DONE | `apps/reporting/views.py` | `test_counsellor_rbac` (3 export cases) | A file is no longer a way to read a report the screen refuses | Counsellor 403, manager 200 with a CSV, trainer 403 | — | 2026-09-06 |
| 12.4 Capability mirror enforced | 12 | DONE | `frontend/tests/unit/capability-mirror.test.ts` | 5 | A typo'd capability name can no longer silently hide a control forever | Verified it fails when a constant is renamed | Parses the backend source; a large refactor of `roles.py` would need the parser revisited | 2026-09-06 |

---

## Cross-cutting gaps carried forward

| Gap | Impact | Owner |
| --- | --- | --- |
| No S3 bucket provisioned | The backend, the privacy rules and the boot guard are built and tested (§14.3); a bucket and credentials are a human step | Engineering |
| No managed Redis | Celery worker and beat run against local Redis and are verified end to end (§14.10); a deployment needs a managed broker | Engineering |
| No real SMTP credentials | Password reset and verification links go nowhere | **Human** |
| No remote; CI has never run on GitHub | Unproven pipeline | **Human** |
| No staging deployment | Release gate | **Human** |
