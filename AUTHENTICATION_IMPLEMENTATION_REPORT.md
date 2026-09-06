# Authentication implementation report

Audit date: 6 September 2026
Auditor: automated code review of the working tree at commit `2a848bd` plus the
uncommitted Phase 11 changes present in the tree.
Method: source inspection of every file in the authentication and authorization
path, plus a full backend test run (`1,339 passed, 2 skipped`) and the frontend
unit suite (`75 passed`).

Nothing in this report is inferred from documentation. Every claim below names
the file that implements it.

---

## 1. Current implementation

### 1.1 Summary

| Question | Answer |
| --- | --- |
| Mechanism | Django server-side **sessions**, cookie-borne, DB-backed |
| JWT | **Not used** anywhere |
| Refresh tokens | **Not used** — not applicable to this architecture |
| Token storage in the browser | None. The session cookie is `HttpOnly`; JavaScript cannot read it |
| CSRF | Enforced, including on anonymous POSTs (login, password reset) |
| Password storage | Django's configured hasher — PBKDF2-SHA256 (Django 5.2 default) |
| Authorization model | Capability matrix resolved from a persisted `role` column |
| Enforcement | Server-side, per view, deny-by-default |
| Audit | Every authentication and account event written to an append-only table |
| MFA | **Not implemented** |

### 1.2 How login works, end to end

1. The browser calls `GET /api/v1/auth/csrf/` (`CSRFTokenView`, anonymous,
   `@ensure_csrf_cookie`). This sets a readable `grras_csrftoken` cookie.
2. The browser POSTs `/api/v1/auth/login/` with `{email, password}` and echoes
   the cookie value in the `X-CSRFToken` header.
3. `LoginView` (`backend/apps/accounts/views.py:63`) is wrapped in
   `EnforceCSRFMixin`, which runs DRF's `SessionAuthentication.enforce_csrf`
   even though the caller is anonymous. This closes the login-CSRF hole DRF
   leaves open by default (`backend/apps/common/mixins.py:14`).
4. `LoginSerializer` validates and lower-cases the email. It is a
   `StrictSerializer`, so unknown fields are rejected rather than ignored.
5. `django.contrib.auth.authenticate` runs the default `ModelBackend`, which
   verifies the password hash and calls `user_can_authenticate` — an inactive
   user fails here, before any session exists.
6. On failure the view returns a single generic `401` with code
   `authentication_failed` and no distinction between "no such account",
   "wrong password" and "account disabled". Django has already fired
   `user_login_failed`, which the audit receiver records.
7. On success `login(request, user)` writes the session row, then
   `request.session.cycle_key()` rotates the session key — session-fixation
   defence.
8. The response body is `CurrentUserSerializer`, which includes the caller's
   resolved `capabilities` list. That list drives what the UI *offers*; it is
   never trusted on the way back in.

### 1.3 Session architecture

- `SESSION_ENGINE = django.contrib.sessions.backends.db` — sessions are rows,
  therefore individually revocable.
- Cookie: `grras_sessionid`, `HttpOnly`, `SameSite=Lax`, `Secure` (forced `True`
  in `hardened.py`, defaulted `True` in `base.py`), 12-hour age,
  `SESSION_SAVE_EVERY_REQUEST = True` giving a sliding expiry.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = False`.
- Revocation: `services.revoke_sessions` (`accounts/services.py`) walks
  non-expired `django_session` rows, decodes each, and deletes those belonging
  to the user. It is called on sign-out-everywhere, role change, email change,
  deactivation and password reset.

### 1.4 Password reset

- `AccountToken` (`accounts/models.py`) stores **only a SHA-256 hash** of a
  256-bit `secrets.token_urlsafe` value. The raw token exists solely in the
  emailed link.
- Issuing a token invalidates the user's outstanding tokens of the same purpose.
- Single use (`used_at` stamped in the consuming transaction), expiring
  (reset: 1 hour; verification: 3 days, both settings-driven).
- Unknown, expired and already-used tokens raise one identical `InvalidTokenError`.
- `request_password_reset` always returns `202` with the same body whether or
  not the address exists, and records `account_exists` in the audit context so a
  reviewer can see probing that the caller cannot.
- A completed reset revokes every session for that user.
- Credential email is sent **inline, not queued** — a deliberate decision
  documented in `accounts/emails.py`: queuing would persist the reset link in
  both the outbox table and the Redis task payload, and the link is the
  credential.

### 1.5 Authorization / RBAC

- `UserRole`: `superadmin`, `admin`, `manager`, `trainer`, `student`.
- `Capability`: ~60 `resource.action` strings in `accounts/roles.py`.
- `ROLE_CAPABILITIES` is the single mapping. Superadmin holds
  `frozenset(Capability.values)` — every capability, including ones added later.
  Admin = base + manager + admin-only. Manager = base + manager set.
  **Trainer and student hold only `BASE_CAPABILITIES`** (view/update own
  profile); everything else they can reach is resolved per record by the
  per-app `access.py` modules.
- `has_capability` returns `False` for anonymous **and for inactive** users.
- Views declare `required_capability` / `capability_map` and use
  `HasCapability`, which **fails closed** if a view names no capability.
- `DEFAULT_PERMISSION_CLASSES = IsActiveUser` — an endpoint is private unless it
  explicitly opts out with `AllowAnyPublic`.
- Object-level: `IsOwnerOrHasCapability` resolves ownership from the object,
  never from a client-supplied id.
- Escalation containment: `can_grant_role` allows granting a role only when its
  capability set is a subset of the actor's own.
- **New in the uncommitted tree:** `can_administer` answers "whose account may I
  touch at all?" — a superadmin may administer anyone (including another
  superadmin, deliberately, so a compromised top account can be disabled);
  everybody else may administer only strictly-lesser roles; nobody administers
  themselves through the staff path. Enforced in the *service* layer
  (`_guard_administration`), so the Django admin and future management commands
  obey it too.

---

## 2. Files involved

### Backend

| File | Role |
| --- | --- |
| `backend/apps/accounts/models.py` | `User` (UUID pk, email login, role, is_active, email verification), `AccountToken` |
| `backend/apps/accounts/managers.py` | `UserManager` — the one creation path for API, admin, commands, migrations |
| `backend/apps/accounts/roles.py` | `UserRole`, `Capability`, `ROLE_CAPABILITIES`, `capabilities_for`, `has_capability`, `can_grant_role`, `can_administer` |
| `backend/apps/accounts/views.py` | Login, logout, logout-all, me, password change, reset request/confirm, email verify request/confirm, profile image |
| `backend/apps/accounts/user_views.py` | User administration: list/create, detail/update, set-active, credential-link, per-user audit |
| `backend/apps/accounts/serializers.py` | Caller-scoped serializers (self vs admin), strict-field enforcement |
| `backend/apps/accounts/services.py` | All state changes + audit, in one transaction each |
| `backend/apps/accounts/signals.py` | `user_logged_in` / `user_logged_out` / `user_login_failed` audit receivers |
| `backend/apps/accounts/emails.py` | Credential mail, sent inline, never logged |
| `backend/apps/accounts/urls.py`, `user_urls.py` | Route tables |
| `backend/apps/common/permissions.py` | `IsActiveUser`, `HasCapability`, `requires()`, `IsOwnerOrHasCapability`, `AllowAnyPublic` |
| `backend/apps/common/mixins.py` | `EnforceCSRFMixin` |
| `backend/apps/common/throttling.py` | `AuthEndpointThrottle` (IP-keyed), `BurstThrottle` (user-keyed) |
| `backend/apps/common/middleware.py` | Request id, client-IP resolution honouring `NUM_PROXIES`, security headers, deferred-audit flush |
| `backend/apps/common/exceptions.py` | One error envelope; `_audit_refusal` records permission-class 403s |
| `backend/apps/common/serializers.py` | `StrictSerializer` / `StrictModelSerializer` / `SafeCharField` |
| `backend/apps/audit/models.py`, `services.py` | Append-only audit log and its single write API |
| `backend/config/settings/base.py` | Cookies, validators, DRF defaults, throttle rates, CSP, token TTLs |
| `backend/config/settings/hardened.py` | Deployed-environment baseline; required secrets; forced secure cookies |
| `backend/config/settings/guards.py` | Boot-time environment/secret/database guards |

### Frontend

| File | Role |
| --- | --- |
| `frontend/lib/api.ts` | The only fetch wrapper; CSRF handshake, `credentials: 'include'`, typed `ApiError`, one stale-CSRF retry |
| `frontend/lib/auth.ts` | Auth calls |
| `frontend/lib/capabilities.ts` | Mirror of the backend capability names, for rendering only |
| `frontend/components/auth-provider.tsx` | Asks `/auth/me/` once on mount; caches the answer |
| `frontend/components/require-auth.tsx` | Navigation aid only; explicitly documented as not a security control |
| `frontend/middleware.ts` | Per-request CSP nonce |
| `frontend/app/login`, `forgot-password`, `reset-password`, `verify-email`, `settings/security` | Screens |

### Tests

`tests/test_auth.py`, `test_password_flows.py`, `test_email_verification.py`,
`test_permissions.py`, `test_security_access_control.py`,
`test_authorization_matrix.py` (160 route×role sweeps), `test_role_hierarchy.py`
(uncommitted, covers `can_administer`), `test_user_admin.py`,
`test_data_and_audit_security.py`, `test_security_config.py`,
`frontend/e2e/auth.spec.ts`, `frontend/e2e/role-administration.spec.ts`
(uncommitted), `frontend/tests/unit/auth-flow.test.tsx`,
`require-auth.test.tsx`, `capabilities.test.ts`.

---

## 3. APIs involved

### `/api/v1/auth/`

| Method | Path | Auth | Throttle | Notes |
| --- | --- | --- | --- | --- |
| GET | `csrf/` | anonymous | default anon | Sets the CSRF cookie |
| POST | `login/` | anonymous | `auth` (10/min/IP) | CSRF enforced; generic 401 |
| POST | `logout/` | active user | — | Idempotent |
| POST | `logout-all/` | active user | — | Deletes every session row for the user |
| GET/PATCH | `me/` | active user | — | PATCH accepts only first/last name and phone |
| GET | `me/email/` | active user | — | Verification status for the settings screen |
| POST/DELETE | `me/profile-image/` | active user | — | Re-encoded, EXIF stripped |
| POST | `password/change/` | active user | `auth` | Requires the current password |
| POST | `password/reset/` | anonymous | `auth` | Always 202, always identical |
| POST | `password/reset/confirm/` | anonymous | `auth` | Single-use token |
| POST | `email/verify/` | active user | `auth` | Resend |
| POST | `email/verify/confirm/` | anonymous | `auth` | Token is the proof |

### `/api/v1/users/`

| Method | Path | Capability |
| --- | --- | --- |
| GET | `` | `user.view_any` |
| POST | `` | `user.create` |
| GET | `<uuid>/` | `user.view_any` |
| PATCH | `<uuid>/` | `user.update_any` (+ `user.change_role` when the role changes, + `can_administer` in the service) |
| POST | `<uuid>/set-active/` | `user.set_active` (+ `can_administer`; self-deactivation refused with 409) |
| POST | `<uuid>/credential-link/` | `user.update_any` (+ `can_administer`) |
| GET | `<uuid>/audit/` | `audit.view` |
| GET | `<uuid>/profile-image/` | any active user |
| DELETE | `<uuid>/profile-image/remove/` | `user.update_any` |

---

## 4. Database models

**`accounts.User`** — UUID pk; `email` unique with an additional
`Lower(email)` unique constraint (blocks case-variant duplicate accounts);
`first_name`, `last_name`, `phone`, `profile_image`; `role` (indexed);
`is_active` (indexed); `is_staff`; `is_email_verified`; `email_verified_at`;
`date_joined`; `created_at`; `updated_at`. Composite index on
`(role, is_active)` and on `-created_at`. Email normalised in both `clean()`
and `save()`.

**`accounts.AccountToken`** — UUID pk; FK to user (CASCADE); `purpose`
(indexed); `token_hash` (unique, `editable=False`); `expires_at`; `used_at`;
`created_at`. Index on `(user, purpose, used_at)`. `__str__` deliberately never
renders the hash.

**`audit.AuditLog`** — UUID pk; `created_at` (indexed); nullable `actor`
(`SET_NULL`) plus denormalised `actor_label`; `action`, `resource_type`,
`resource_id` (all indexed); `result`; `ip_address`; `user_agent`;
`request_id` (indexed); `request_method`; `request_path`; `context` JSON.
`save()` refuses updates, `delete()` raises, and the queryset's `delete`/`update`
raise as well. `purge_before` is the only removal path.

**`django_session`** — Django's own table, used as the session store.

No `Role` or `Permission` table exists. Roles are a column and capabilities are
code. That is a deliberate design (`roles.py` docstring) and is a genuine
trade-off, discussed in §7.

---

## 5. Security strengths

1. **Deny by default at the framework level.** `IsActiveUser` is the DRF
   default, and `HasCapability` refuses a view that names no capability. A new
   endpoint is private unless someone writes code to make it public.
2. **One authorization table.** No role string comparison is scattered through
   views. `test_authorization_matrix.py` sweeps every route against every role.
3. **Authorization decided in the service layer, not only the view.**
   `_guard_administration` and the role checks in `update_user` mean the Django
   admin and management commands cannot bypass the rules.
4. **Privilege-escalation containment.** `can_grant_role` (subset rule) plus
   `can_administer` (strict-subset rule on the target) close both the "mint a
   superadmin" and the "edit the superadmin's email, then reset it" paths.
5. **Login CSRF is closed.** `EnforceCSRFMixin` runs the check on anonymous
   POSTs, which DRF does not.
6. **No account enumeration.** Login, password reset and token consumption all
   return one answer for every failure mode. `AuthenticationFailed` is
   normalised in the central exception handler as well.
7. **Reset tokens are stored hashed.** A database read cannot be turned into
   account takeover.
8. **Session fixation defeated** by `cycle_key()` after login.
9. **Immediate revocation on privilege change.** Role change, email change,
   deactivation and password reset all delete existing sessions.
10. **Append-only audit log** with actor label denormalised so history survives
    account deletion, and a `scrub()` pass at the single write point so no
    caller can persist a secret.
11. **Failed authorization is audited even when no view wrote it** —
    `_audit_refusal` in the exception handler, deduplicated against view-level
    entries via `denial_already_recorded()`.
12. **Deferred audit writes survive rollback.** `ATOMIC_REQUESTS` is on, so
    failure entries are queued and flushed by middleware *after* the
    transaction ends.
13. **Serializers are scoped by caller, not by resource.** `SelfUserUpdateSerializer`
    physically cannot accept `role`, `is_active`, `is_staff`, `is_superuser` or
    `email`, and `StrictSerializer` returns 400 naming an unknown field rather
    than silently discarding it — mass assignment is structurally impossible.
14. **Boot-time guards.** A deployed environment refuses to start with a
    placeholder secret, a short secret, SQLite, a missing shared cache, eager
    Celery, or a public S3 bucket.
15. **Security headers** are set and asserted: CSP (nonce-based on the
    frontend), `X-Frame-Options: DENY`, nosniff, referrer policy, COOP,
    Permissions-Policy, HSTS in deployed environments.
16. **Client IP is resolved honestly** — `NUM_PROXIES` bounds how much of
    `X-Forwarded-For` is trusted, so a client cannot spoof its address to evade
    the rate limit or poison the audit trail.
17. **Media is never web-served.** Profile images go through an authenticated
    view that forces `image/jpeg` and `nosniff`.
18. **Administrators never handle other people's passwords.** There is no "set
    their password" control; only "send a link".

---

## 6. Security weaknesses

Ordered by risk.

### W1 — No multi-factor authentication (medium-high for an admin surface)
There is no TOTP, WebAuthn or email-code second factor. A stolen admin password
is full admin access. Documented as a known gap in `docs/RELEASE_READINESS.md`,
not an oversight, but it remains the largest single weakness for a system where
`superadmin` can reach every record.

### W2 — Brute-force protection is per-IP only, with no per-account limit (medium)
`AuthEndpointThrottle` keys on the client IP (`get_ident`). There is no
per-account counter and no lockout. Consequences:
- Password spraying from a botnet — one attempt per IP against thousands of
  accounts — is not bounded at all.
- A slow, distributed attack on one known admin address is not bounded either.
- Conversely, users behind one corporate NAT share the 10/min budget.

The audit log *records* the pattern (`auth.login.failed` with `actor_label`), so
it is detectable after the fact, but nothing acts on it.

### W3 — `SameSite=Lax` constrains the deployment topology (medium, latent)
The frontend calls the API cross-origin with `credentials: 'include'`. `Lax`
cookies are not sent on cross-**site** subrequests. This works today because the
frontend and API share a registrable domain (`localhost`, and by design the
staging/production hostnames). If the API is ever moved to a different
registrable domain from the frontend, **every authenticated request will
silently fail**, and the fix (`SameSite=None; Secure`) reintroduces the CSRF
exposure that the current setting mitigates. This is a constraint nobody has
written down as a constraint.

### W4 — `revoke_sessions` is an O(all sessions) full scan (medium, performance/availability)
Django's session table is keyed by session key with the user id inside the
encoded payload, so the function iterates every non-expired row and decodes it.
It is called on **every** role change, email change, deactivation, password
reset and sign-out-everywhere. The docstring acknowledges this and says "move to
a session backend that indexes the user id if the table grows". At a few
thousand concurrent sessions this becomes a multi-second request inside
`ATOMIC_REQUESTS`. It is also unbounded, so it is a plausible self-inflicted
denial of service on a busy install.

### W5 — Reset and verification tokens travel in the URL query string (low-medium)
`emails.py::_build_link` produces `?token=…&email=…`. Query strings land in
browser history, in any frontend access log, and in the `Referer` header of
subresource requests from that page. The frontend's Next middleware sets CSP but
does **not** set a `Referrer-Policy`, so the default (`strict-origin-when-cross-origin`
in modern browsers) is what protects it — by browser default, not by
configuration. Mitigated by the 1-hour TTL and single use.

### W6 — Password hashing is PBKDF2, not Argon2id (low)
`PASSWORD_HASHERS` is not overridden outside tests, so Django's default
PBKDF2-SHA256 applies. That is acceptable and FIPS-friendly, but Argon2id is the
stronger modern default and `argon2-cffi` is not in `requirements/`. Worth a
deliberate decision rather than an unexamined default.

### W7 — Login does not require a verified email (low, by design but unstated)
`is_email_verified` is recorded and surfaced but never gates authentication. A
user created by an administrator receives a set-password link, so in practice
the first sign-in implies inbox control; but a user created *with* a password
(the `create_user(password=…)` path, used by seeds) can sign in unverified.
There is no policy switch for this.

### W8 — Any authenticated user can fetch any other user's profile image (accepted risk)
`ProfileImageFileView` allows any active user to read `/users/<uuid>/profile-image/`.
Documented as deliberate ("names and faces are visible across the platform").
It is an enumeration oracle for *which user ids have images*, nothing more,
since ids are UUIDv4. Listed for completeness.

### W9 — No session inventory for the user (low)
"Sign out everywhere" exists, but a user cannot see *what* is signed in — no
device/last-seen list. So a user who suspects compromise can only nuke
everything, and cannot notice a foreign session in the first place.

### W10 — `.env` with a real local password sits in the working tree (low, local only)
`.env` is correctly git-ignored (`.gitignore:4-7`) and `gitleaks` is wired into
`make secrets`. Only `*.example` files are tracked. No leak; noted because
`vidyansh.pem` is also present in the tree (also git-ignored).

### Not weaknesses (checked and clear)

- **IDOR** — object-level checks resolve ownership from the object; the
  authorization matrix suite includes cross-tenant cases.
- **Mass assignment** — strict serializers, per-caller field lists.
- **SQL injection** — ORM throughout; no raw SQL in the auth path.
- **Stack traces** — the central handler answers 500s with a generic message
  plus a request id.
- **Secrets in logs** — `RedactSecretsFilter` on the log handler and `scrub()`
  at the audit write point; `test_data_and_audit_security.py` asserts it.
- **Revoked sessions still working** — they cannot; the row is deleted and
  `IsActiveUser` re-checks on every request.

---

## 7. Missing functionality

Relative to a production ERP, and relative to the requirements in the brief:

| Missing | Impact |
| --- | --- |
| **`COUNSELLOR` role** | The brief's five roles are Admin, Manager, Trainer, Counsellor, Student. Four exist (plus `superadmin`). Counsellor does not, and neither do the capabilities its workflow needs (student registration → course selection → batch creation → trainer assignment). |
| MFA / TOTP | See W1 |
| Per-account brute-force limit and lockout | See W2 |
| Session inventory / device list | See W9 |
| Password history / reuse prevention | Only "must differ from current" is enforced, on change but not on reset |
| Password expiry policy | None. Arguably correct (NIST advises against forced rotation), but unstated |
| Machine/API tokens | No non-browser client path exists. `docs/architecture.md` names it as planned |
| Impersonation ("sign in as") with audit | Common ERP support need; absent |
| Soft delete for users | Users are deactivated, never deleted. There is **no soft-delete infrastructure anywhere in the codebase** (no `deleted_at`/`deleted_by`/`delete_reason` on any model) |
| A `Permission` table | Capabilities are code constants. Adding a capability or re-mapping a role requires a deploy, not a configuration change |
| Per-batch / per-branch organisational scoping | Authorization is role + per-record assignment. There is no "organisational unit" concept, so a manager sees the whole institution |

---

## 8. Bugs

**No functional bugs were found in the authentication path.** The full backend
suite passes (1,339 tests) including the uncommitted Phase 11 work, and the
frontend unit suite passes (75 tests).

Two correctness observations that are not bugs today but are latent:

- **B1 (latent).** `update_user` computes `changed` by comparing
  `getattr(user, field) != value` *after* `_guard_administration`, but the
  authority check uses the target's **current** role. Since a role change is
  additionally gated by `can_grant_role` this is safe. It is worth a test that
  asserts an admin cannot use a single PATCH to both raise a target's role and
  then act on the raised role — the current code cannot, but nothing pins it.
- **B2 (latent).** `revoke_sessions` catches bare `Exception` around
  `get_decoded()` and continues. Correct behaviour, but if the SECRET_KEY is
  rotated, *every* session becomes undecodable and the function silently
  reports 0 revocations while logging a warning per row. A rotation would
  produce a very loud log and a misleading "Signed out of 0 session(s)" message.

---

## 9. Recommended changes

Ordered by value per unit of risk. None of these require rewriting anything.

**Do before adding ERP features (Phase 2 of the plan):**

1. **Add the `COUNSELLOR` role** to `UserRole` and `ROLE_CAPABILITIES`. This is
   genuinely a one-entry change by design — plus the new capabilities its
   workflow needs (`student.create` it already implies, plus batch creation and
   trainer assignment). Add it to `frontend/lib/capabilities.ts` and to
   `test_authorization_matrix.py`'s role sweep in the same change.
2. **Add a per-account login throttle** alongside the per-IP one. A second
   `SimpleRateThrottle` keyed on the *submitted* email (hashed, to avoid a cache
   full of addresses) with a slower rate, plus a temporary lockout after N
   failures within a window. Both counters already have a shared Redis cache to
   live in.
3. **Write down the `SameSite=Lax` topology constraint** in
   `docs/architecture.md` and add a boot-time warning in `hardened.py` when
   `FRONTEND_BASE_URL` and `ALLOWED_HOSTS` do not share a registrable domain.

**Do during hardening (Phase 14):**

4. **Bound `revoke_sessions`.** Either (a) add a `UserSession` table keyed by
   `(user, session_key)` written in a `user_logged_in` receiver and deleted
   alongside, or (b) move to a session backend that indexes the user. Option (a)
   is small, additive, and also gives you W9's device list for free.
5. **Add MFA for `admin` and `superadmin`** at minimum. TOTP via
   `django-otp` is the least-surprise choice and does not disturb the session
   architecture.
6. **Switch to Argon2id** (`argon2-cffi` in `requirements/base.txt`, Argon2
   first in `PASSWORD_HASHERS`). Django rehashes on next login automatically.
7. **Set an explicit `Referrer-Policy` in `frontend/middleware.ts`** so token
   URLs are protected by configuration rather than by browser default.

**Consider, with a decision recorded either way:**

8. Password-reuse prevention on reset (not only on change).
9. An `is_email_verified` login gate behind a settings flag, off by default.
10. Audited impersonation for support.

---

## 10. Risk level

| Area | Risk | Reasoning |
| --- | --- | --- |
| Authentication mechanism | **Low** | Session + CSRF, correctly implemented, no token-handling mistakes possible because there are no client-held tokens |
| Credential storage | **Low** | Hashed passwords, hashed single-use tokens, no secrets in logs or audit |
| Authorization / RBAC | **Low** | Deny-by-default, one matrix, service-layer enforcement, 160-test route sweep |
| Privilege escalation | **Low** | Both the grant rule and the target rule are closed; every refusal audited |
| Account takeover via reset | **Low** | Hashed, superseding, single-use, 1-hour tokens; sessions revoked on use |
| Brute force / credential stuffing | **Medium** | W2: no per-account limit, no lockout |
| Account compromise impact | **Medium** | W1: no MFA, so one password is one account |
| Availability | **Medium-low** | W4: `revoke_sessions` full scan |
| Deployment misconfiguration | **Low** | Boot guards refuse the dangerous configurations outright |
| Data exposure | **Low** | Serializers assert field-by-field in `test_data_and_audit_security.py` |

**Overall authentication risk: LOW-MEDIUM.** The implementation is materially
better than typical for a project at this stage. The residual risk is
concentrated in two named, well-understood gaps (MFA, per-account rate limiting)
rather than spread across the design.

---

## 11. What can be reused

Essentially all of it. Specifically, the ERP build should reuse:

- `apps.accounts.roles` — add roles and capabilities here; do not create a
  parallel permission system.
- `apps.common.permissions.HasCapability` / `requires()` /
  `IsOwnerOrHasCapability` — every new view.
- `apps.common.mixins.EnforceCSRFMixin` — any new anonymous POST endpoint.
- `apps.common.serializers.StrictSerializer` / `StrictModelSerializer` /
  `SafeCharField` — every new serializer.
- `apps.common.exceptions` — the error envelope; raise `ApplicationError`,
  `ConflictError`, `AuthorityError` from services and let the handler shape them.
- `apps.audit.services.record` — the only way to write an audit entry. Add new
  `AuditAction` members; never build `AuditLog` directly.
- `apps.common.throttling.BurstThrottle` — every export and import endpoint.
- `apps.common.pagination.DefaultPagination` / `stable_order` — every list.
- `apps.common.models.BaseModel` — every new domain model.
- `apps.common.uploads` + `apps.common.scanning` + `apps.common.storage` — every
  file upload.
- `apps.common.middleware` request-id and IP resolution.
- `frontend/lib/api.ts` (`apiFetch`, `apiMutate`, `fieldErrors`,
  `errorMessage`, `queryString`) — every frontend call. Do not write a second
  client.
- `frontend/hooks/use-list.ts`, `use-api.ts`; `components/list-toolbar.tsx`,
  `pagination.tsx`, `states.tsx`, `ui/*` — every new screen.
- `frontend/components/navigation.ts` (uncommitted) — the nav registry.

---

## 12. What must be changed

- `apps/accounts/roles.py` — add `COUNSELLOR` to `UserRole`, define its
  capability set, and add the new capabilities the ERP workflows need
  (DSR review, attendance override scoping, performance review, export job
  management). This is an **additive** change to the existing matrix.
- `frontend/lib/capabilities.ts` — mirror the additions.
- `tests/test_authorization_matrix.py` and `tests/test_role_hierarchy.py` —
  extend the role sweep to the new role; the suites are structured to make this
  a data change.
- `apps/common/throttling.py` — add the per-account login throttle (W2).
- `apps/accounts/services.py::revoke_sessions` — bound it (W4), when the
  session-inventory table lands.
- `config/settings/base.py` — `PASSWORD_HASHERS` (W6), if Argon2 is adopted.
- `docs/architecture.md` / `docs/security.md` — record the `SameSite` constraint
  and the MFA decision.

---

## 13. What must NOT be changed

Touching any of these would remove a defence that is currently working:

1. **The session architecture.** Do not introduce JWTs. There are no
   client-held tokens today, which is why there is no token-leak, token-revocation
   or refresh-rotation problem to solve. Adding JWTs would create all three.
2. **`EnforceCSRFMixin` on anonymous POST views.** Removing it reopens login CSRF.
3. **`request.session.cycle_key()` after login.** Session fixation defence.
4. **The generic-failure responses** in `LoginView`, `request_password_reset`
   and `_consume_token`. Making any of them more informative reintroduces
   account enumeration.
5. **Token hashing in `AccountToken`.** Never store or log a raw token.
6. **Inline (unqueued) credential email.** Queuing it would persist reset links
   in the outbox table and in Redis.
7. **`DEFAULT_PERMISSION_CLASSES = IsActiveUser`.** Changing it to `AllowAny`
   would silently open every endpoint that forgot to declare permissions.
8. **`HasCapability` failing closed when no capability is named.**
9. **`can_grant_role` and `can_administer`.** Both close real, demonstrated
   escalation paths (see `docs/DECISIONS.md` D-095…D-100).
10. **The append-only guards on `AuditLog`** (`save`/`delete`/queryset
    `delete`/`update`).
11. **`ATOMIC_REQUESTS = True` + the deferred-audit flush in middleware.**
    They work as a pair; removing the deferral loses every failure audit entry.
12. **The boot-time guards** in `config/settings/guards.py` and `hardened.py`.
13. **`StrictSerializer`'s unknown-field rejection** and the separate
    self/admin serializers.
14. **Media served only through authenticated views** (never `MEDIA_URL` in a
    deployed environment).
15. **`NUM_PROXIES`-bounded IP resolution.**

---

## 14. Completion percentages

Scored against a production ERP standard, not against "does it work".

### Authentication: 90%

| Area | % | What the remaining percent is |
| --- | --- | --- |
| **Login** | 95% | Complete and correct. −5 for no per-account throttle/lockout (W2) and no optional verified-email gate (W7) |
| **Logout** | 100% | Single logout, sign-out-everywhere, idempotent, CSRF-protected, audited, sessions actually deleted |
| **Sessions** | 85% | Correct and revocable. −10 for the O(n) revocation scan (W4), −5 for no session inventory (W9) |
| **RBAC** | 80% | Excellent structure; deny-by-default; ladder proven monotonic. −15 for the missing `COUNSELLOR` role, −5 for no organisational scoping |
| **Permissions** | 90% | ~60 capabilities, per-record access layers, 160-test matrix. −10 because capabilities are code, not data, so re-mapping needs a deploy |
| **Password reset** | 95% | Hashed, single-use, expiring, superseding, non-enumerating, sessions revoked. −5 for token-in-query-string (W5) and no reuse prevention |
| **Security** | 80% | −10 no MFA (W1), −5 per-IP-only rate limiting (W2), −5 PBKDF2 rather than Argon2id (W6) |
| **Audit logging** | 95% | Append-only, scrubbed, request-correlated, survives rollback, covers permission-class refusals. −5 because there is no retention job wired and no alerting on the failure patterns it records |

**Weighted overall: Authentication 90%.**

The 10% gap is four named items: MFA, per-account brute-force limiting, the
`COUNSELLOR` role, and bounded session revocation. Nothing needs to be rebuilt
to close any of them.
