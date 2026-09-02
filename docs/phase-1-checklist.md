# Phase 1 — completion checklist

**Status: complete.** Identity, users, students and trainers are built, tested
and verified against a running stack.

Last verified: 2026-08-31 · 220 backend tests (91% coverage) · 34 frontend unit tests · 12 end-to-end tests

| Symbol | Meaning |
| --- | --- |
| ✅ | Done and verified by a test, a scan or a live run |
| 🟡 | Foundation in place, full feature intentionally deferred |
| ⬜ | Deferred — out of scope for this phase |

---

## §1 Scope

| Item | Status |
| --- | --- |
| Authentication | ✅ |
| User management | ✅ |
| Roles | ✅ |
| Permissions | ✅ |
| Student management | ✅ |
| Trainer management | ✅ |
| User profile management | ✅ |
| Account status | ✅ |
| Admin management interface | ✅ |
| Audit logging integration | ✅ |
| API endpoints | ✅ |
| Frontend interfaces | ✅ |
| Test coverage | ✅ |
| Staging seed data | ✅ |
| Courses / batches / assignments / exams / attendance / certificates / payments / CRM / HR / placement | ⬜ not built, as instructed |

**Requested addition:** fee **status** on the student record (`pending`,
`partial`, `paid`, `waived`, `overdue`) — administrator-maintained, audited,
filterable, read-only to students. Scoped deliberately as a status flag, not an
accounting system: amounts, transactions and receipts belong with the payments
module so there is only ever one source of truth about money.

---

## §2 User model

| Requirement | Status | Notes |
| --- | --- | --- |
| Reuse the Phase 0 custom user model | ✅ | Extended, not replaced |
| No second user model | ✅ | One `AUTH_USER_MODEL` |
| Admin / Trainer / Student | ✅ | `UserRole` |
| Extensible to more roles | ✅ | One entry in `ROLE_CAPABILITIES` |
| ID, email, password, first/last name, phone, profile image | ✅ | |
| Is active, date joined, last login, created, updated | ✅ | |
| Database constraints | ✅ | Case-insensitive unique email; composite indexes on `(role, is_active)` and `created_at` |
| Explicit email uniqueness | ✅ | `UniqueConstraint(Lower("email"))` |
| Public identifiers, not internal IDs | ✅ | UUID primary keys plus `GRS-S-…` / `GRS-T-…` |

---

## §3–4 Authentication

| Requirement | Status |
| --- | --- |
| Login | ✅ |
| Logout | ✅ (plus sign-out-everywhere) |
| Password reset | ✅ request + confirm, single-use expiring token |
| Password change | ✅ requires current password |
| Email verification | ✅ request + confirm |
| Current-user endpoint | ✅ `/auth/me/` with capability list |
| Session/token invalidation | ✅ four mechanisms, documented |
| Account activation/deactivation | ✅ separate audited endpoint |
| Invalid credentials handled | ✅ identical response for every reason |
| Inactive account handled | ✅ indistinguishable from a wrong password |
| Expired reset token | ✅ |
| Used reset token | ✅ |
| Invalid verification token | ✅ |
| Rate-limit violations | ✅ 429 with `retry_after_seconds` |
| No enumeration via password reset | ✅ identical 202, tested |
| No secrets in responses | ✅ no serializer exposes `password` |
| One authentication strategy | ✅ session only |
| Browser auth documented | ✅ `docs/authentication.md` §1 |
| API auth documented | ✅ §2 |
| Logout/invalidation documented | ✅ §4 |
| Expiry documented | ✅ §5 |
| Refresh documented | ✅ §5 — none used, and why |
| No auth logic in UI components | ✅ transport in `lib/`, decisions on the server |

---

## §5–6 Roles and permissions

| Requirement | Status | Notes |
| --- | --- | --- |
| ADMIN / TRAINER / STUDENT | ✅ | |
| No hard-coded role checks scattered about | ✅ | One capability matrix |
| Reusable permission architecture | ✅ | `HasCapability`, `requires()`, `IsOwnerOrHasCapability` |
| User management permissions | ✅ | view/create/update/set-active/change-role |
| Student management permissions | ✅ | view/create/update/set-fee-status |
| Trainer management permissions | ✅ | view/create/update |
| Profile management permissions | ✅ | view own / update own |
| Trainer cannot manage users | ✅ | tested |
| Student cannot access other students | ✅ | tested |
| Enforced on the backend | ✅ | frontend hides only |

---

## §7–9 Profiles

| Requirement | Status |
| --- | --- |
| Student profile linked to user | ✅ `StudentProfile` |
| Student ID | ✅ `GRS-S-00042`, sequence-allocated |
| Date of birth, address, city, state, country | ✅ optional |
| Education, institution, qualification | ✅ optional |
| Emergency contact, guardian information | ✅ optional |
| Profile completion status | ✅ computed, not stored |
| Internal notes | ✅ administrator-only, never returned to the student |
| Gender | ⬜ deliberately not collected (see `docs/security.md` data minimisation) |
| Trainer profile linked to user | ✅ `TrainerProfile` |
| Trainer ID, title, bio, skills, expertise, qualifications, experience | ✅ |
| Professional links | ✅ HTTPS-only, key-allowlisted |
| Active status | ✅ `is_accepting_assignments`, separate from account status |
| Prepared for course/batch assignment | ✅ skills + availability, no scheduling built |
| Users edit only permitted fields | ✅ enforced in three layers |
| Cannot modify ID, status, role, timestamps | ✅ tested per field |

---

## §10–11 Listing and account management

| Requirement | Status |
| --- | --- |
| Search | ✅ name, email, student ID, trainer ID |
| Filtering | ✅ role, status, verification, fee status, qualification, city, skill, experience |
| Sorting | ✅ server-side, on indexed columns |
| Pagination | ✅ server-side, capped at 100 per page |
| Active/inactive filtering | ✅ |
| Role filtering | ✅ |
| Activate / deactivate user | ✅ |
| View user, view role | ✅ |
| Inactive account fails authentication | ✅ tested |
| Existing access handled | ✅ next request refused; stored sessions deleted |
| Action audited | ✅ |

---

## §12–14 Frontend

| Page | Status |
| --- | --- |
| `/login` | ✅ |
| `/forgot-password`, `/reset-password` | ✅ |
| `/verify-email` | ✅ |
| `/admin/users` | ✅ table with search, filter, sort, pagination, activate/deactivate |
| `/admin/students` | ✅ table + create dialog + inline fee status |
| `/admin/trainers` | ✅ table + create dialog + availability toggle |
| `/profile` | ✅ role-aware: student or trainer form |
| `/settings/account` | ✅ status and email verification |
| `/settings/security` | ✅ password change, sign out everywhere |
| Loading / empty / error / success / validation-error / permission-denied states | ✅ all six |
| Student learning dashboard | ⬜ later phase, as instructed |
| Trainer course-management screens | ⬜ later phase, as instructed |

---

## §15–16 API and audit

| Requirement | Status |
| --- | --- |
| Follows the existing versioning strategy | ✅ `/api/v1/` |
| `/auth/`, `/users/`, `/students/`, `/trainers/` | ✅ |
| No endpoint bypasses permission checks | ✅ deny-by-default; a view with no declared capability denies |
| Validation, pagination, filtering | ✅ |
| Consistent error format | ✅ one envelope |
| HTTP status correctness | ✅ 400/401/403/404/409/429 |
| No stack traces to clients | ✅ generic 500 + request id |
| Login success / failure audited | ✅ |
| Logout audited | ✅ |
| Password changes audited | ✅ incl. failed attempts |
| User creation audited | ✅ |
| Activation/deactivation audited | ✅ |
| Role changes audited | ✅ separately, for easy review |
| Student / trainer profile changes audited | ✅ with changed field list |
| Fee status changes audited | ✅ with from/to and actor |
| No passwords, tokens, reset tokens or secrets logged | ✅ tested |

---

## §17 Security review

| Threat | Status |
| --- | --- |
| Broken access control | ✅ |
| IDOR | ✅ |
| Privilege escalation | ✅ |
| Account enumeration | ✅ |
| Brute-force login | ✅ |
| Session issues | ✅ |
| CSRF | ✅ incl. the anonymous-POST gap DRF leaves open |
| Unsafe file uploads | ✅ |
| Excessive data exposure | ✅ |
| Mass assignment | ✅ |
| Direct modification of role/status fields | ✅ |

### Defects found during Phase 1 and fixed

| # | Defect | Fix |
| --- | --- | --- |
| 1 | `ATOMIC_REQUESTS` + DRF's rollback on handled exceptions discarded **failure audit entries** — the audit row for a rejected token or wrong password was rolled back with the failure it recorded | Non-success entries are queued and written by middleware outside the request transaction |
| 2 | DRF's session-auth CSRF check produced a different error code from the explicit mixin, and echoed the server-side reason ("CSRF token missing") | Both paths normalised to `csrf_failed` with the reason stripped |
| 3 | `user.has_capability` broke for `AnonymousUser`, silently dropping views from the generated OpenAPI schema | Views use the module-level `has_capability()` helper, which handles every user type |
| 4 | The frontend container healthcheck used `localhost`, which resolves to `::1` inside the container while the Node server binds IPv4 only — the container reported unhealthy while serving traffic normally | Healthcheck uses `127.0.0.1` in both compose files |

---

## §18 Profile image uploads

| Requirement | Status |
| --- | --- |
| Restrict file types | ✅ JPEG/PNG/WEBP; SVG rejected |
| Validate file size | ✅ 2 MB, plus a pixel-dimension cap |
| Validate actual content | ✅ opened and verified with Pillow |
| Safe server-side filenames | ✅ UUID, sharded path |
| Client filename not trusted | ✅ discarded entirely |
| Prevent executable uploads | ✅ tested with a PHP payload |
| Access control enforced | ✅ authenticated callers only |
| Not public by default | ✅ media never web-served |
| Upload tests | ✅ 13 tests |

---

## §19 Database

| Requirement | Status |
| --- | --- |
| Indexes on email, student ID, trainer ID, active status, role | ✅ |
| No unnecessary indexes | ✅ composite indexes chosen to match real queries |
| Foreign-key constraints | ✅ |
| Transactions for multi-step operations | ✅ account + profile creation is atomic, tested |

---

## §20 Testing

| Area | Status |
| --- | --- |
| Authentication | ✅ |
| Permissions | ✅ |
| Student CRUD | ✅ |
| Trainer CRUD | ✅ |
| User CRUD | ✅ |
| Profile updates | ✅ |
| Activation/deactivation | ✅ |
| Password workflows | ✅ |
| File upload | ✅ |
| Pagination | ✅ |
| Filtering | ✅ |
| Authorization failure | ✅ |

Mandatory security tests, all present and passing:

| Test | Status |
| --- | --- |
| Student cannot access another student | ✅ |
| Student cannot access restricted trainer information | ✅ |
| Trainer cannot access admin functions | ✅ |
| Trainer cannot change role | ✅ |
| Student cannot change role | ✅ |
| Inactive users cannot authenticate | ✅ |
| Anonymous users cannot access protected APIs | ✅ |

---

## §21–22 Seed data and acceptance

| Requirement | Status |
| --- | --- |
| 2 admin users | ✅ |
| 5 trainers | ✅ |
| 20 students | ✅ |
| Realistic but fake profiles | ✅ `@demo.grras.invalid` (RFC 2606 reserved) |
| Never production data | ✅ no import path exists |
| Idempotent | ✅ users *and* profiles |

| Acceptance criterion | Status |
| --- | --- |
| Admin / trainer / student can authenticate | ✅ verified live |
| Password reset works | ✅ |
| Email verification works | ✅ |
| Admin can manage users / students / trainers | ✅ |
| Students and trainers update permitted fields | ✅ |
| Unauthorized access rejected | ✅ |
| Backend permissions enforced | ✅ |
| Audit logs work | ✅ |
| Profile image handling secure | ✅ |
| API documentation updated | ✅ |
| Tests pass | ✅ 266 total |
| Security tests pass | ✅ |
| CI passes | 🟡 all checks pass locally; never executed on GitHub (no remote) |
| Staging seed works | ✅ |
| Staging deployment works | ✅ verified in Phase 0; unchanged and re-validated by config tests |
| Documentation updated | ✅ |

---

## Outstanding — requires a human

1. Provide real SMTP credentials. Until `EMAIL_HOST` and friends are set in a
   deployed environment, password reset and verification links go nowhere.
2. Push to a remote and confirm the first CI run is green.
3. Confirm the fee-status vocabulary matches how Grras actually tracks fees.
4. Decide whether trainers should see the students in their batches — currently
   they see nobody, which is correct until batches exist.
5. Provision staging infrastructure and re-run the staging validation with real
   secrets.

---

## Next phase

See the Phase 2 recommendation in the implementation report: courses and batches
built on these profile models, with enrollment as the join between them.
