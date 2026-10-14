# Current project status and role guide

Snapshot date: **12 October 2026**
Local baseline: `main` at `cd00122` (25 September 2026)
Purpose: one short, current guide to what is built, who owns each workflow, and
what should be agreed before the next implementation pass.

This document describes the code that is on local `main`. Work on remote
feature branches is listed separately and must not be treated as shipped.

## 1. Status in one page

The project is a mature training-institute ERP and LMS, not a new build. The
25-phase ERP programme is present on `main`, including dynamic roles and
permissions, centre scoping, MFA, sessions, policies, forms, activities,
Student 360, performance and risk, automation, communications, exports,
recovery, dashboards, analytics, and role-specific workspaces.

| Area | Current status | Evidence on `main` |
| --- | --- | --- |
| Backend | Built; 41 Django apps and 156 migrations | `backend/apps/`, `backend/config/api_urls.py` |
| Frontend | Built; 96 routed pages | `frontend/app/` |
| Authorization | Built; capability, object and centre checks | `backend/apps/accounts/roles.py`, `backend/apps/authorization/`, domain `access.py` files |
| Navigation | Built; capability-driven sidebar and mobile drawer | `frontend/components/navigation.ts`, `frontend/components/app-shell.tsx` |
| Frontend quality | Green locally on 12 Oct | 142 files / 1,318 tests; lint and typecheck passed |
| Backend quality | 3,515 tests collect; last documented full run was 3,451 passed, 4 skipped | A fresh run needs PostgreSQL; no local server was running during this audit |
| Browser tests | 19 Playwright spec files exist | Latest release specs have not been re-run against a live stack |
| CI | Red on `main` and the active feature branch | GitHub created the runs but reported no jobs/logs; this looks like a workflow or platform-startup failure, not a proven test failure |
| Production | Not ready for public launch | See the release blockers below |

### Work that is not on `main`

Remote `feat/counsellor-ux` is 17 commits ahead of `main` as of 7 October. It
adds enquiries, assigned forms, a richer class report, instalments, payment
references, follow-ups, attendance modes, and a showcase dataset. It currently
has no product pull request and its latest CI run is red. Treat it as
**development in progress**, not part of the baseline described below.

## 2. The role boundary that exists today

The server is authoritative. The sidebar only hides links for convenience; it
does not grant or deny access.

| Role | Current reach | Clear boundary |
| --- | --- | --- |
| Trainer | 3 global self-service capabilities plus access resolved from assigned courses, batches, classes, students and activities | May teach and assess only where assigned. Cannot manage institution-wide people, data, policy or exports. |
| Counsellor | 62 capabilities, centre-scoped | Cannot create or edit trainers, manage trainer requirements, or view policy settings. Otherwise it currently holds almost every manager operation. |
| Manager | 66 capabilities, centre-scoped | Adds trainer create/edit, trainer requirements and policy viewing. Cannot manage accounts, roles, institution settings, recovery or platform controls. |
| Administrator | 91 capabilities, unbounded across centres | Adds account/role/policy/organisation management, recovery, certificates, sessions, forms, automation and templates. Cannot lock permission grants, change platform branding/configuration or permanently purge. |
| Superadmin | All 94 capabilities, unbounded | The only role that may lock grants, change platform-wide configuration and permanently purge records. |

The main boundary problem is therefore specific: **manager and counsellor are
not separate operational roles today**. The code intentionally makes them
near-equals and relies on different sidebar ordering to suggest different jobs.
Only these four capabilities separate them:

- `trainer.create`
- `trainer.update_any`
- `requirement.manage`
- `policy.view`

That is a valid design if either role is expected to cover the other. It is not
a clear boundary if counsellors should own admissions while managers should own
academic delivery. Changing it is a product decision because it will revoke
working access and invalidate existing role tests, custom-role seeds and user
expectations.

## 3. Natural role flows

### Counsellor: bring a student in

1. Open **Admissions dashboard** (`/admissions/dashboard`).
2. Check registrations and possible duplicates.
3. Use **Register a student** (`/admissions/new`).
4. Choose the course and batch, record the agreed fee and first payment.
5. Open the student record (`/admissions/[studentId]`).
6. Plan and complete follow-ups, update fees, or transfer the enrolment.
7. Hand the enrolled student to the teaching team.

Recommended ownership: admissions, student contact details, enrolment, fees,
follow-ups and transfers. A counsellor should be able to read the course,
batch and trainer information needed to place a student, but should not publish
courses, correct attendance, review daily reports, or manage assessments.

### Manager: run academic operations

1. Open **Manager overview** (`/manage`).
2. Check at-risk students, overdue work, reports awaiting review and attendance
   warnings.
3. Open **Batch review**, **Trainer review** or **Reviews due**.
4. Open Student 360 (`/manage/students/[enrollmentId]`) for the full learning
   record and the reason behind performance or risk values.
5. Assign follow-up work, review activities and daily reports, and resolve
   trainer or batch problems.

Recommended ownership: trainers, batches, schedules, attendance corrections,
daily-report review, academic work, performance, risk and operational reports.
The manager may oversee admissions and fees, but the normal write path should
stay with the counsellor.

### Trainer: deliver assigned learning

1. Open **Today's class** (`/teaching/today`).
2. Select a class and take attendance.
3. Record the topic, class report and activities.
4. Create or grade assignments, weekly tests, projects and examinations for
   assigned batches.
5. Use **My work** (`/teaching/work`) for pending and overdue activities.

Boundary: assignment is the source of authority. A trainer must not gain
institution-wide access merely because a sidebar link is visible.

### Administrator: govern the system

1. Open **Overview** (`/admin/overview`) and **Activity review**.
2. Manage users, roles, permission scopes, centres and sessions.
3. Configure policies, forms, activity types, automation, communication,
   institution settings and academic rules.
4. Manage approvals, certificates, exports and deleted-record recovery.
5. Use operational screens for support or intervention, not as the normal
   owner of daily counselling or teaching work.

Boundary: an administrator governs the institution but cannot perform the
three superadmin-only actions: permission locking, platform configuration and
permanent purge.

## 4. Sidebar and naming convention

Use plain job language. A label should describe the record or action without
requiring knowledge of the codebase.

### Route namespaces

| Namespace | Meaning | Keep? |
| --- | --- | --- |
| `/admissions/*` | Counsellor workflow | Yes |
| `/manage/*` | Manager workflow | Yes |
| `/teaching/*` | Trainer workflow | Yes |
| `/admin/*` | Administration and configuration | Yes |
| `/my-*` | Student-owned information | Yes |

Do not rename stored role values, capability codes or existing URLs for a
cosmetic wording change. Change user-facing labels first; add redirects only
when a URL is genuinely misleading.

### Recommended label changes

| Current label | Prefer | Reason |
| --- | --- | --- |
| Review | Performance | Says what is being reviewed |
| Manager's work | Academic operations | Describes the job, not the person |
| Counsellor's work | Admissions | Matches the workflow and route |
| Authoring | Courses | Familiar noun; the page can still say “Edit course” |
| Outcomes | Results and reports | Names the contents |
| Performance and outcomes | Results and reports | Shorter and concrete |
| Everyday | Updates | “Everyday” does not predict what is inside |
| Today | Today's class | Avoids a context-free date word |
| Classes today | Today's classes | Natural reading order |

Split **My profile** into an **Account** group when practical. Keep
Announcements and Notifications under **Updates**. Avoid duplicate destinations
with different labels in the same role's sidebar.

### Code naming

- Django apps, TypeScript modules and URLs: lower-case nouns; use hyphens in
  URLs and snake_case in Python fields.
- Capabilities: `<resource>.<action>`, for example `student.create`.
- React components and types: PascalCase. Functions, hooks and variables:
  camelCase.
- User-facing actions start with a verb: **Register student**, **Record
  payment**, **Review report**, **Restore record**.
- Prefer **student**, **trainer**, **course**, **batch**, **class**, **fee** and
  **report**. Avoid synonyms such as learner/instructor/program/cohort/session
  when they refer to those same domain objects.
- Keep the existing British spelling **Counsellor** unless the whole product is
  deliberately moved to US English. Do not mix both spellings in the UI.

## 5. Reuse these models

The project already has the right core models. The next pass should extend
them rather than create role-specific duplicates.

| Need | Reuse | Do not add yet |
| --- | --- | --- |
| Identity and access | `User`, dynamic `Role`, `Capability`, `ScopeGrant` | Separate `ManagerProfile` or `CounsellorProfile` |
| Prospect before registration | `Enquiry` from the active feature branch, after review | A second temporary-student table |
| Registered person | `StudentProfile` + `Enrollment` | A duplicate admissions student model |
| Follow-up or staff action | Generic `Activity` + versioned `FormResponse` | One model per follow-up type |
| Fees | Per-enrolment fee ledger and instalments | A gateway-shaped payment model until online payments are required |
| Teaching | `Batch`, `BatchSchedule`, `ClassSession`, `AttendanceRecord`, `DSR` | A parallel class-tracking module |
| Learning work | `Assignment`, `Assessment`, `Project`, `Exam` | Generic blobs that lose each workflow's rules |
| Governance | `AuditLog`, `Policy`, `AutomationRule`, `Delivery`, `ExportJob` | Untracked admin actions |

## 6. Implementation order

1. **Agree the manager/counsellor boundary.** Choose whether the current shared
   access is intentional or move to job-owned writes.
2. **Secure routes first.** Update the capability matrix, object-level access,
   centre scope and audit tests before hiding or showing links.
3. **Simplify navigation.** Apply the label changes, remove duplicate
   destinations, and keep the mobile drawer and keyboard behavior.
4. **Integrate active feature work.** Bring the enquiry/counsellor branch
   through a reviewed product PR; do not merge it while CI cannot start.
5. **Verify every role.** Run the capability matrix, role hierarchy, frontend
   suite and the six-role Playwright crawl against a seeded stack.
6. **Finish release infrastructure.** Only then call the project production
   ready.

## 7. Release blockers

- GitHub Actions is red and currently creates failed runs with no jobs or logs.
- Production domain and trusted TLS certificate are not configured.
- Real SMTP credentials are not configured.
- Managed Redis, production object storage/backup bucket and least-privilege
  database roles still need provisioning.
- The live database restore and new-host disaster-recovery drills still need a
  supervised run.
- MFA exists, but no role is currently required to enrol by policy.
- The malware-scanning hook exists, but no scanner is configured.
- The newest browser journeys have not been run against a live stack.
- The student-facing **My activities** page is still missing on `main`.

## 8. Decision needed before permission implementation

Recommended target: **job-owned writes with supervised read access**.

- Counsellor writes admissions, enrolment, fees, follow-ups and transfers.
- Manager writes academic operations, trainer/batch management, reviews and
  performance actions; may read admissions and fees for oversight.
- Trainer writes only within assigned teaching records.
- Administrator configures and supports all centres; superadmin keeps the
  three irreversible/platform controls.

If the intended policy is instead “manager and counsellor can cover each
other,” keep the current capability overlap and make the distinction a sidebar
and dashboard preference only. The UI must then say that clearly rather than
presenting the roles as security boundaries.
