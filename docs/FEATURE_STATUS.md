# Feature status

The working task board. One row per feature. A row is `DONE` only when it is
tested and verified running — not when the code exists.

**Statuses:** `TODO` · `IN_PROGRESS` · `BLOCKED` · `DONE`

Totals at last full run: **511 backend** (92% coverage) · **59 frontend unit** ·
**35 end-to-end** = 605 tests, all passing.

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
| 4.3 Assignments | 4 | TODO | `apps/assignments/` | — | — | — | — | — |
| 4.4 Assignment file security | 4 | TODO | `apps/common/uploads.py` | — | — | — | — | — |
| 4.5 Weekly tests / external assessments | 4 | TODO | `apps/assessments/` | — | — | — | — | — |
| 4.6 Trainer result import | 4 | TODO | `apps/assessments/importers.py` | — | — | — | — | — |
| 4.7 Academic configuration | 4 | TODO | `apps/academics/` | — | — | — | — | — |

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

## Cross-cutting gaps carried forward

| Gap | Impact | Owner |
| --- | --- | --- |
| No S3 wired — files sit on a container volume | Blocks production file handling; Phase 9 item | Engineering |
| No Celery/Redis worker — nothing runs asynchronously | Blocks email retry and heavy reports; Phase 9 item | Engineering |
| No real SMTP credentials | Password reset and verification links go nowhere | **Human** |
| No remote; CI has never run on GitHub | Unproven pipeline | **Human** |
| No staging deployment | Release gate | **Human** |
