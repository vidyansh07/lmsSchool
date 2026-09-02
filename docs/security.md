# Security

The baseline follows OWASP ASVS principles. This document states what is
implemented today, where it lives, and what is explicitly deferred.

**The governing rule: never trust the frontend.** The UI may hide what a user
cannot use — that is convenience. Every sensitive decision is made by the
backend, on every request.

---

## 1. Secret management

- No secret is committed. `.env*` files are git-ignored; only `*.example`
  templates are tracked.
- Secrets reach deployed environments through the platform's secret manager as
  process environment variables. They are never baked into an image, never
  written to a file in the repository, and never passed on a command line.
- Each environment has its own secret set. Reusing a production secret in
  staging would defeat the isolation staging exists to provide.
- `DJANGO_SECRET_KEY` must be at least 50 characters with at least 5 distinct
  characters, and must not contain the development placeholder marker. A weak
  or shared key raises `ImproperlyConfigured` at boot, not at review time.
- The local Docker stack has no default database password: `docker compose up`
  fails until `POSTGRES_PASSWORD` is set.
- CI runs **gitleaks** across the working tree and full history on every pull
  request. Allowlisted patterns are limited to provable non-secrets (template
  files, the reserved `@demo.grras.invalid` domain, documented fake DSNs).

Generate a key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## 2. Authentication

- Email + password, with Django's password hashing (PBKDF2 by default;
  configurable per environment).
- Password policy: minimum 12 characters, plus Django's similarity, common-password
  and numeric-only validators.
- Sessions: `HttpOnly` (JavaScript cannot read the credential, so XSS cannot
  exfiltrate it), `SameSite=Lax`, `Secure` everywhere except plain-HTTP local
  development, 12-hour lifetime with sliding expiry.
- The session key is cycled on login, which defeats session fixation.
- Login responses are identical for "no such account" and "wrong password", so
  the endpoint cannot be used to enumerate accounts.
- Inactive users cannot authenticate, and an active session stops working as
  soon as the account is deactivated.
- Login is rate limited (default 10/min per client IP, `THROTTLE_RATE_AUTH`).

---

## 3. Authorization

- **Deny by default.** `IsActiveUser` is the project-wide default permission
  class, so an endpoint is private unless it explicitly opts out with
  `AllowAnyPublic` — a marker chosen so every public route is grep-able during
  review.
- **Capabilities, not scattered role checks.** `apps/accounts/roles.py` holds one
  table mapping roles to capabilities; views declare the capability they need. A
  role missing from the table gets only base self-service rights, so an
  incompletely configured role fails closed.
- Roles are read from the persisted user record, never from a request header,
  body or cookie claim.
- **Object-level ownership** (`IsOwnerOrHasCapability`) is checked on every
  record fetched by id. Ownership is resolved from the object, never from a
  client-supplied identifier — this is what closes IDOR: guessing another
  student's UUID returns 403, not their data.
- **Separately-authorised sensitive actions.** Changing a role needs
  `user.change_role` on top of edit rights; account activation and fee status
  each have their own endpoint and capability, so neither can be flipped as a
  side effect of editing a phone number.
- An administrator cannot deactivate their own account (409), which would lock
  the platform's last operator out.

---

## 3a. Mass assignment and privilege escalation

The attack named in the specification — `{"role": "ADMIN"}` — fails, and fails
*loudly*:

```
PATCH /api/v1/auth/me/   {"role": "admin"}
→ 400 {"error": {"code": "validation_error",
                 "details": {"role": ["This field is not accepted."]}}}
```

Three layers produce that:

1. **Serializers are scoped by caller.** `SelfUserUpdateSerializer` lists exactly
   `first_name`, `last_name`, `phone`. An administrator editing someone else uses
   a different class entirely.
2. **Unknown fields are rejected, not ignored** (`StrictFieldsMixin`). Silent
   ignoring hides both client bugs and attacker probing.
3. **Services take an explicit `allowed_fields` set** derived from the caller's
   authorization level, never from the request body, so no serializer bug can
   widen it.

Never self-editable by anyone: `role`, `is_active`, `is_staff`, `is_superuser`,
`email`, `is_email_verified`, `student_id`, `trainer_id`, `fee_status`, `notes`,
`is_accepting_assignments`, and every timestamp.

Administrator-only data is also excluded from the *read* path: a student's own
profile serializer has no `notes` field at all, so internal notes cannot reach
the person they are about.

---

## 4. Input validation and output handling

- Serializers validate everything at the boundary. `StrictSerializer` rejects
  unknown fields rather than ignoring them, which surfaces both client bugs and
  attacker probing.
- Shared validators reject control characters and enforce conservative name and
  phone formats. Input is rejected, not sanitised — silent "cleaning" hides
  attacks.
- Model validators and database constraints back-stop non-API paths (admin,
  management commands, data migrations).
- The API renders JSON only; DRF's JSON renderer escapes content, and the ORM
  parameterises every query. React escapes by default and the project uses no
  `dangerouslySetInnerHTML`.
- Upload size limits are configured (`DATA_UPLOAD_MAX_MEMORY_SIZE`, default
  5 MB) and uploaded files are stored outside the web root with restrictive
  permissions. See §5a for the profile image pipeline.

---

## 5. CSRF

- Django's CSRF middleware is enabled and the CSRF cookie is readable by the
  SPA so it can echo the token in `X-CSRFToken`.
- `CSRF_TRUSTED_ORIGINS` is an explicit list; there is no wildcard.
- DRF marks API views `csrf_exempt` and defers the check to session
  authentication, which only runs once a session user exists. That leaves
  endpoints accepting anonymous POSTs — login above all — unprotected by
  default, enabling login CSRF. `apps.common.mixins.EnforceCSRFMixin` closes
  that gap and is applied to the login endpoint. **Any future endpoint that
  accepts an unauthenticated unsafe request must use it.**
- CSRF failures return the standard error envelope with code `csrf_failed` and
  no server-side token state.

---

## 5a. File uploads (profile images)

Every rule here exists because the naive version of it is a known vulnerability.
Implemented in `apps/common/uploads.py`.

| Control | Why |
| --- | --- |
| Client filename discarded entirely; the stored name is a server-generated UUID | Blocks path traversal (`../../etc/passwd`), double extensions (`avatar.php.jpg`) and characters that confuse a web server |
| Declared `Content-Type` ignored; bytes opened and verified with Pillow | `Content-Type` is client-supplied and proves nothing |
| Allowlist of JPEG, PNG, WEBP — **SVG rejected** | SVG is XML, can carry script, and is not safe to serve as an image |
| Re-encoded to a fixed-size JPEG rather than stored as uploaded | Strips EXIF (which routinely carries GPS coordinates), normalises the format, and neutralises polyglot files that are simultaneously a valid image and a valid script |
| Size limit (2 MB) and pixel-dimension limit checked before decoding | Prevents decompression bombs |
| Stored under `MEDIA_ROOT`, which is never web-served | The only read path is an authenticated Django view |
| Served with a forced `image/jpeg` type, `nosniff` and `Content-Disposition: inline` | A stored file can never be reinterpreted as another content type |
| Replacing an image deletes the previous file | No orphaned personal data |

Anonymous callers cannot read any uploaded file. Signed-in users can see each
other's profile photos, which is deliberate: names and faces are visible across
the platform.

---

## 5b. Course resource uploads

Course resources are documents, not images, so they cannot be re-encoded the
way profile photos are — there is no lossless "re-save a PDF" that neutralises
embedded content. The defence is different, and layered:

| Control | Why |
| --- | --- |
| Extension allowlist (PDF, Office, ZIP, images, plain text) | Everything else is refused outright |
| Explicit deny-list checked first (`.php`, `.jsp`, `.html`, `.svg`, `.exe`, `.sh`, …) | Names the refusal unambiguously during a review |
| Magic-byte check **paired with the extension** | `.docx`, `.pptx`, `.xlsx` and `.zip` are all ZIP containers, so a signature alone proves nothing — the *pair* is validated |
| Plain text proven to decode as UTF-8 with no NUL bytes | A binary renamed `.txt` is refused |
| Server-generated storage name; client filename kept for display only | Blocks traversal, double extensions and control characters |
| 25 MB limit | Bounded work |
| Stored under `MEDIA_ROOT`, never web-served | The only read path is an authenticated view |
| Served `attachment` with `nosniff` and a **server-built** filename | A malicious resource title cannot be echoed into a response header, and nothing is ever rendered in the browser |

ZIP is accepted deliberately (§6 "where explicitly allowed") for exercise
bundles. It is never unpacked by the server.

---

## 5c. Content access and video

Course content has its own access question, separate from "may I see this
course exists?". `apps/courses/access.py` answers both, and every route asks it
rather than deciding for itself.

* **Unpublished content is invisible, not merely uneditable.** A student
  requesting a draft course by id or slug gets 404 — the record is resolved
  inside a queryset they are entitled to, so it is not in their world at all.
* **Filtering happens at every level.** A draft lesson inside a published module
  inside a published course is still hidden. Filtering one level up and not the
  next is exactly where this kind of gap appears.
* **Video URLs are issued, not published.** `VideoAsset.source_url` appears in
  no list or detail payload. A caller who is entitled to watch fetches it from
  `/lessons/<id>/video/`, which re-checks access first — so a private asset URL
  is never sprayed across a catalogue response.
* **The application container stores no video bytes.** Providers are modelled
  (external URL, S3, managed service) so hosting can move without a migration.

---

## 5d. Course access through enrolment

From Phase 3, course content is gated on a real enrolment. All four conditions
must hold, and `Enrollment.grants_access()` is the single place they live:

1. the account is active;
2. the enrolment status is `active` or `completed`;
3. the batch is not cancelled;
4. today is inside the access window, where one is set.

Consulted live on every request, so suspending an enrolment or cancelling a
batch closes access on the very next call — there is no cache to invalidate and
no second copy of the rule to forget.

Cancelling never deletes: the enrolment row and its progress survive, the audit
entry records `history_preserved: true`, and a returning student finds their
history intact.

---

## 6. Transport, cookies and headers

| Control | Deployed environments | Local |
| --- | --- | --- |
| `SECURE_SSL_REDIRECT` | on | off (plain HTTP) |
| HSTS | 1 year + subdomains + preload (production); 1 hour, no preload (staging) | off |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | on | off |
| `SECURE_PROXY_SSL_HEADER` | `X-Forwarded-Proto` | same |
| `X-Frame-Options` | `DENY` | `DENY` |
| `X-Content-Type-Options` | `nosniff` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | same |
| `Cross-Origin-Opener-Policy` | `same-origin` | same |
| Content-Security-Policy | restrictive, `frame-ancestors 'none'` | same |
| `Permissions-Policy` | geolocation/microphone/camera denied | same |

Staging deliberately omits HSTS preload: preload submission is effectively
permanent and wrong for an environment that is torn down and rebuilt. Django's
`security.W021` is silenced for that documented reason in staging only.

The frontend sets its own CSP and security headers in `next.config.ts`; the two
origins are independent in production, so neither relies on the other's headers.

CORS uses an explicit origin allowlist with `CORS_ALLOW_CREDENTIALS = True`. A
wildcard origin is never used, and would be invalid with credentials anyway.

---

## 7. Rate limiting

DRF throttling with named scopes: `anon`, `user`, `auth` (credential checks)
and `burst` (reserved for future expensive endpoints). Rates are environment
variables, so each environment can be tuned without a code change.

Counters live in the Django cache. Local development uses in-process memory;
**deployed environments must set `CACHE_URL`** and will refuse to boot without
it, because per-worker counters would silently multiply every limit by the
worker count.

Client IP resolution honours only as many proxies as `NUM_PROXIES` declares.
Trusting the whole `X-Forwarded-For` chain would let a client spoof its address
and defeat both rate limiting and audit attribution.

---

## 8. Error handling

- One error envelope for every failure.
- Unhandled exceptions log a full traceback server-side and return a generic
  message plus a request id. Exception text, stack frames, SQL, DSNs and
  settings never reach the client.
- `DEBUG` is hard-coded to `False` in every deployed settings module — it is
  not an environment variable there.
- Django's default HTML error pages are replaced with JSON handlers that follow
  the same rules.
- Health endpoints return component status only: no hostnames, no versions, no
  configuration.

---

## 9. Logging and audit

- Structured logs with a request id on every line; JSON format in deployed
  environments.
- A redaction filter scrubs known-sensitive keys (`password`, `token`,
  `secret`, `authorization`, `cookie`, `api_key`, …) from structured context
  before anything is written, recursively and depth-limited.
- The audit log records actor, action, resource, result, timestamp, request id,
  IP, user agent, method and path. Its context is scrubbed at the single write
  point, so no caller can persist a secret by accident.
- Failed logins are recorded with the attempted username only — never a
  candidate password.
- Password reset and verification tokens are never logged and never written to
  an audit record; only the *reason* a token was rejected (unknown, expired,
  used) is stored.
- **Failure entries survive the rollback that produced them.** `ATOMIC_REQUESTS`
  plus DRF's rollback on handled exceptions would otherwise discard the audit
  row for a failed action along with the action itself. Non-success entries are
  queued and written by middleware after the request transaction ends.
- Audit records are append-only: updates and deletes raise, and the admin is
  read-only.
- Dedicated `grras.security` and `grras.audit` log channels exist so those
  events can be shipped to a SIEM separately.

---

## 10. Dependencies

- Backend dependencies are pinned exactly; the frontend has a committed
  lockfile. Upgrades go through a pull request so every scan re-runs.
- CI runs `pip-audit --strict`, `npm audit --audit-level=high` and `bandit`.
- Dependabot proposes weekly updates, grouped for minor/patch.
- Both images run as unprivileged users. The backend runtime image contains no
  build toolchain.

---

## 11. What is deliberately not built yet

Named so nobody assumes a control exists that does not:

| Not implemented | Notes |
| --- | --- |
| Multi-factor authentication | Planned for administrator accounts |
| Account lockout after repeated failures | Rate limiting only, today |
| Token authentication for non-browser clients | Foundation is ready; unused auth is unreviewed attack surface |
| Changing your own email address | Needs its own verified, re-authenticated flow |
| Antivirus scanning of uploads | The hook exists and is tested (`apps/common/scanning.py`); no scanner is configured, and an unreachable one refuses the upload |
| Document uploads (ID proof, certificates) | The upload pipeline exists; no endpoint uses it yet |
| Signed video URLs for S3 / managed providers | Modelled and routed, but only the external-URL provider is playable today |
| Virus scanning of course resources | Same hook, same state: wired, unconfigured |
| Per-file download rate limiting | `burst` is attached to exports and bulk imports (§14.4); individual file downloads are still on the ordinary user limit |
| Field-level encryption at rest | Database-level encryption is a deployment concern |
| Automated audit retention | `purge_before` exists; no scheduler yet |
| WAF / DDoS protection | Edge concern, handled by the hosting platform |

---

## 11a. Phase 1 security test coverage

`backend/tests/test_security_access_control.py` tests each attack directly:

| Attack | Test |
| --- | --- |
| Broken access control | Anonymous callers refused on every protected route; students and trainers refused on every admin route |
| IDOR | Student cannot read or edit another student; cannot read a trainer; trainer cannot read a student or another trainer |
| Privilege escalation | `{"role": "admin"}`, `is_staff`, `is_superuser`, `is_active`, `is_email_verified` all rejected on the self endpoint |
| Mass assignment | `fee_status`, `student_id`, `trainer_id`, `notes`, `is_accepting_assignments` rejected from self-service |
| Excessive data exposure | Internal notes absent from a student's own view; no serializer exposes `password` or `is_superuser` |
| Account enumeration | Login and password-reset responses proven identical for known and unknown addresses |
| Brute force | Login and reset endpoints rate limited |
| Session issues | Deactivation effective on the next request; reset and change revoke other sessions |
| CSRF | Anonymous POST endpoints proven to require a token; both CSRF paths normalised to one code |
| Unsafe upload | PHP-as-PNG, SVG, oversized, empty and content-type-lying uploads all rejected; filename discarded; EXIF stripped |
| Fail-closed authorization | An unknown role and a view that declares no capability both deny |

`backend/tests/test_courses_security.py` covers the Phase 2 surface:

| Attack | Test |
| --- | --- |
| Unauthorised unpublished content | Draft courses absent from the catalogue; 404 by id and by slug; draft modules, lessons and resources unreachable; a draft lesson inside a published course hidden; private courses invisible |
| IDOR | A trainer assigned to one course cannot read or edit another, nor add content to it, nor edit a module belonging to it; a random UUID 404s without a traceback |
| Privilege escalation | Students cannot create, edit, publish or archive; trainers hold no global course capability; an editor cannot publish, only submit for review; removing an assignment removes the access immediately |
| Mass assignment | `status`, `code`, `published_at`, `created_by`, `content_updated_at` refused on the course editor; `position` and `status` refused on the lesson editor |
| Unsafe upload | PHP, double-extension, SVG, HTML, shell script, executable, content/extension mismatch, binary-as-text, empty and oversized files all refused |
| Malicious filenames / traversal | `../../../etc/passwd.pdf` never reaches the filesystem; the download filename is built by the server and carries no injected quotes or second extension |
| Public file exposure | `MEDIA_ROOT` is not web-served; downloads require authentication *and* content entitlement |
| Excessive API data | Video source URLs absent from every payload; instructor emails absent; lesson summaries carry no body |

`backend/tests/test_enrollment_security.py` and
`test_course_access_by_enrollment.py` cover the Phase 3 surface:

| Attack | Test |
| --- | --- |
| Enrolling somebody else | A student cannot enrol themselves or another student; a trainer cannot enrol at all |
| Reading another student's enrolment | 404 by id; the list is filtered; the administrative status note is absent from a student's view |
| Changing your own standing | A suspended student cannot reactivate themselves |
| Trainer overreach | Cannot see, edit, schedule or take a roster on an unrelated batch; cannot edit even their own; cannot self-assign |
| Batch id manipulation | Guessed ids 404 across batches, rosters, enrolments and schedules; filters cannot widen visibility |
| Access after losing an enrolment | Suspension, cancellation and batch cancellation each close content access on the next request, with no body leaked in the refusal |
| Cross-course access | An enrolment on one course opens no other |
| Mass assignment | `status`, `code`, `trainer` and `created_by` refused on the batch editor; a client-supplied `course_id` refused on enrolment |
| Roster privacy | A student cannot list their classmates |

---

## 13. Object storage (Phase 9, §14.3)

Student files are private wherever they are stored, and the storage backend is
configuration: `FILE_STORAGE_BACKEND=local` on a laptop, `s3` in a deployment.
No application code knows which is in use.

Three properties, and none of them relies on the deployment being set up
correctly by hand:

- **No public URL.** `PrivateMediaStorage` sets `default_acl = None`, so an
  upload never stamps an ACL of its own and the bucket policy is the single
  place access is decided. `querystring_auth` stays on, so `storage.url()`
  returns a URL that carries a signature and expires (300 seconds by default).
- **No direct hand-off.** Downloads are still served by the application after an
  authorization check, exactly as they were on local disk. A signed URL is a
  bearer token in an address bar — it lands in history, in referrers, and in
  whatever a student pastes into a chat — so it stays the storage API's
  fallback, not the delivery path.
- **No public bucket.** `check_storage_configuration` refuses to boot a deployed
  environment configured with a public ACL or with unsigned URLs. The failure it
  prevents is silent: uploads work, and the files are readable by anyone who can
  guess a key.

Credentials are read by boto3 from the environment or the instance role, and are
never named in a settings file. Prefer the instance role.

Verified by `backend/tests/test_file_storage_security.py`, which runs the real
backend against a mocked bucket: a file goes in, comes back byte-for-byte, its
URL is signed and expiring, and its object ACL grants nothing to `AllUsers`.

### Malware scanning

`apps/common/scanning.py` is the seam a scanner attaches to. It answers the two
questions that matter before a scanner exists:

- **Infected** — the upload is refused with a message that says only that a
  security scan rejected it. The signature name goes to the audit log, never to
  the uploader: telling somebody *which* detection fired turns the endpoint into
  an oracle for tuning a payload until it passes.
- **Scanner unavailable** — refused, by default. `UPLOAD_SCAN_FAIL_OPEN` can
  reverse that, and should not be. Failing open means an attacker bypasses
  scanning entirely by taking the scanner down.

Rejections are audited as `file.upload.rejected`.

---

## 14. Background work (Phase 9, §14.10)

Celery over Redis, with one producer: email. The queue is deliberately small —
every queued job is something that can be lost, retried twice or silently
backlogged.

- **The outbox is written inside the request; only the send is queued.** If the
  broker is unreachable, the row still exists and still says PENDING, so the
  message is late rather than lost. A broker error never reaches the caller: a
  Redis blip must not fail a grading request.
- **`task_acks_late` with a prefetch of one.** A worker killed mid-send has its
  task redelivered rather than dropped. `send_queued_email` re-reads the row and
  checks its status first, so a redelivery is a no-op instead of a second email.
- **A scheduled sweep is the net.** `notifications.retry_pending_email` runs on
  beat every five minutes and is the only path by which a message queued during
  a provider outage ever arrives. Exactly one beat process, ever — two means
  every retry is sent twice.
- **No result backend.** Task results would keep recipient addresses in Redis
  for no reader.
- **Eager mode is refused in a deployed environment.** It runs "background" work
  inside the request that queued it, which is the failure the queue exists to
  prevent.

**Credential email is deliberately not queued.** The body of a password-reset
message *is* the credential, and both halves of the queue would store it: the
outbox row in a database table, the task payload in Redis. Reset and
verification mail is sent inline, on endpoints already rate-limited to a handful
of requests a minute. See `apps/accounts/emails.py`.

Exports and bulk imports were considered and left synchronous: exports already
stream in constant memory, and imports are bounded to 2,000 rows and must be
all-or-nothing inside one transaction. Both decisions are recorded in
`docs/DECISIONS.md` with the trigger for revisiting them.

---

## 15. Database privileges (Phase 9, §14.8)

`infra/db/least-privilege.sql` creates two roles:

| Role | Used by | May |
| --- | --- | --- |
| `grras_migrate` | `manage.py migrate` | Own and change the schema |
| `grras_app` | Web workers, Celery worker | Read and write rows. No DDL. |

`grras_app` cannot CREATE in `public`, is not a superuser, and cannot UPDATE or
DELETE `audit_auditlog` — history is append-only from the application's point of
view, and editing it is the first thing an intruder would want to do. Future
tables inherit the row grants through `ALTER DEFAULT PRIVILEGES`, so a new model
does not arrive unreadable.

The script was applied to a scratch database and its grants verified with
`has_table_privilege` before being committed; the transcript of what was checked
is in the file's header comment.

---

## 16. Dependency policy (Phase 9, §14.7)

CI fails on `pip-audit --strict`, `npm audit --audit-level=high`, `bandit` and
`gitleaks`. A high-severity advisory is not waived silently: if one cannot be
fixed by upgrading, the exception goes in `docs/DECISIONS.md` naming the
advisory, why the code is not reachable by it, and what mitigates it in the
meantime. There are no such exceptions today.

---

---

## 17. Reporting a vulnerability

Report privately to the maintainers. Do not open a public issue. Include the
request id from the error response where relevant — it identifies the incident
without exposing anything sensitive.
