# Security decisions — ERP platform

Builds on `docs/security.md` (the LMS controls: session cookies, CSRF on
anonymous POSTs, CSP with a per-request nonce, private uploads re-encoded
and scanned, throttles, scrubbed logs, audited 403s, least-privilege DB
roles). Every item below is a decision, not an aspiration; the phase that
delivers it is named.

## Authentication (Phases 4–6)

- **Session cookies stay the only credential** (D-002). MFA and step-up add
  states to the session; they never mint tokens.
- **Password policy** from policy category `password`: min length (floor 8,
  default 10), require classes (default 2 of 4), reject breached (HIBP
  k-anonymity, optional, off until network egress is decided), history 5,
  max age (default none). Django validators are configured from the policy
  at request time; changing the policy never weakens below the floor.
- **Login lockout**: existing `auth` throttle (10/min per IP) plus a per-user
  counter in the cache (policy `authentication.lockout_after`, default 10
  failures in 15 min → 15-minute lock). Locked accounts get the same
  response as a wrong password; the lock is audited and visible to admins.
- **MFA**: TOTP (RFC 6238, 30 s step, ±1 step tolerance, last-step replay
  guard) and email OTP. Required per role by policy `mfa.required_roles`
  (default `["superadmin", "admin"]` once Phase 5 lands, applied only
  after the role's users have enrolled — a grace of `mfa.grace_days`,
  default 7, during which login shows an enrol banner). Recovery codes: ten,
  hashed, single use, regenerate invalidates all.
- **Pending-MFA session**: after a correct password the session holds only
  `mfa_pending` for 5 minutes; every endpoint except `auth/mfa/*` and
  `auth/csrf/` treats it as anonymous.
- **Step-up**: `session.step_up_at`; required within `auth.step_up_minutes`
  (default 10) for: purge, permission lock/unlock, role delete, MFA disable,
  critical policy changes, template approval for WhatsApp, revoking another
  admin's sessions. Obtained by re-entering the password or a factor. The
  API answers `403 step_up_required` and the UI opens the step-up dialog
  in place, then retries the original request once.

## OTP (Phase 4)

- 6 digits from `secrets.randbelow`; stored as SHA-256(salt + code);
  10-minute expiry; 5 verification attempts then the code is void; resend
  no sooner than 60 s; 5 sends per user per hour, 20 per IP per hour;
  consumption under `select_for_update` so two concurrent verifies cannot
  both succeed (tested).
- Never logged: the scrubber denylist already contains `otp`; the email
  body is built in the channel and not stored in `Delivery.variables`.
- Audited: `otp.sent`, `otp.verified`, `otp.failed`, `otp.throttled` with
  the purpose, never the code.

## Authorization (Phases 1–2)

- **Catalog in code, mapping in rows** (ADR-01). A view can only require a
  capability that exists in the enum; a row cannot invent one.
- **Scopes narrow only** (ADR-02). The role kind is the floor; a configured
  scope is applied on top inside `visible_*`. No scope is ever read from
  the client.
- **Locks** (ADR-03): lockable permissions, locked grants, superadmin +
  step-up to change. `record.purge` and `platform.configure` are seeded
  locked to superadmin and refused to any other kind by the service.
- **Ladder invariants** kept: `can_grant_role` and `can_administer` compare
  effective sets; a custom role wider than the granter's cannot be granted
  (tested with a custom role that adds `audit.view` to a manager kind and
  a manager trying to assign it).
- **Cache**: version-keyed; every write bumps on commit; a stale grant can
  outlive its revocation by at most one in-flight request (ADR-14). The
  denial path is never cached separately from the grant path.
- **Every 403 audited** centrally (D-075) — including `step_up_required`.

## Sessions (Phase 6)

- `UserSession` records the hash of the key, never the key. Listing shows
  device label, IP, created, last seen, "this device". Revoke one, revoke
  all others, revoke all. Admins with `session.revoke_any` may revoke a
  user's sessions within scope (step-up required); the user is emailed.
- New-device login (unknown user-agent family + IP /24 for that user)
  sends `security_event`.
- Session age from policy `session.max_age_hours` (default 12, floor 1,
  ceiling 168); idle timeout `session.idle_minutes` (default none).

## Rate limiting

Existing scopes stay. New: `otp` 5/min per IP on `auth/mfa/*`; `search`
120/min per user; `communication` 30/min per user on manual sends;
`automation_test` 10/min.

## Uploads (Phase 8)

Form `file`/`image` fields go through `apps/common/uploads.py` (re-encode
images, extension-pair documents, scan when a scanner is configured,
refuse when it is unavailable — D-068). Accept lists and max size come from
policy `file_upload` with a hard ceiling of 25 MB. Downloads stay behind the
application (D-067) with the same `visible_*` check as the owning record.

## Exports and search

- Exports re-scope in the worker to the requester (existing). A custom
  scope (`assigned`, `own`) is applied there too.
- Global search only federates `visible_*` querysets; no direct model
  queries; results carry no fields the list endpoint would not.
- Both audited: `data.exported` (existing) and `search.performed` (query
  length and type counts only, never the query text — it may contain a
  name).

## Dynamic content

- Form field labels/help, template bodies, announcement bodies, activity
  summaries: stored as text, rendered escaped; `richtext` fields pass an
  allowlist sanitiser (tags p, br, strong, em, ul, ol, li, a[href https],
  code, pre). Never `dangerouslySetInnerHTML` without the sanitiser.
- Template rendering substitutes allowlisted variables only (ADR-12). Any
  `{{` outside the allowlist renders as empty and is flagged in preview.
- Automation conditions and actions are data with a closed vocabulary
  (ADR-13). No `eval`, no expressions.
- Relation fields resolve through `visible_*` so a form cannot become an
  existence oracle for ids outside the caller's reach.

## Secrets and provider credentials

- Only from the environment: `MFA_ENCRYPTION_KEY`, `WHATSAPP_*`, SMTP,
  `AWS_*`. Never a row, never a policy value, never logged (scrubber
  denylist extended with `access_token`, `phone_number_id`, `secret`).
- The template builder shows provider template *ids* only.
- Webhooks verify a shared token and, where the provider offers it, an
  HMAC signature; unverified payloads are dropped and counted.

## Soft delete and audit

- Every ERP table a person can delete is soft-deletable; the bin lists
  them by kind; purge is superadmin + step-up + reason.
- Audit never stores secrets (scrubbed context) and never stores form
  values for fields typed `file`/`image` beyond the upload id.
- Change history for Role, Permission, Policy, Form, ActivityType,
  Activity, Review, DSR, attendance corrections is the audit `changes`
  context, rendered as who/what/when/why.

## Destructive and expensive actions (§8, 72, 73)

| Action | Confirmation | Step-up | Permission |
| --- | --- | --- | --- |
| Soft delete | dialog with reason | no | per resource |
| Purge | typed confirmation (record label) + reason | yes | record.purge |
| Lock/unlock permission | dialog naming the role and permission | yes | permission.lock |
| Delete role | dialog; refused while users hold it | yes | role.manage |
| Critical policy change | dialog with the old and new value | yes | policy.manage |
| Disable MFA (own or another's) | dialog | yes | self / user.update_any |
| Bulk attendance change | dialog with count and scope | no | attendance.correct_any |
| Send WhatsApp / mass email | dialog with recipient count and template | no | communication.send |
| Export > sync limit | dialog with row count and destination | no | data.export |
| Activate automation | dialog with the last 7 days' match count | no | automation.manage |
| Publish form / template | dialog | no | form.manage / template.manage |

The frontend distinguishes intents in code: `ConfirmDialog` takes
`intent: "mutation" | "destructive" | "expensive"` and refuses to render a
destructive dialog without a `confirmLabel` and `reason` field.

## Threats and controls (§54)

| Threat | Control |
| --- | --- |
| IDOR | queryset-first resolution (rule 2) everywhere, including timeline, search, form relations, deliveries |
| Privilege escalation | ladder invariants over effective sets; locked grants; superadmin-only seeds; step-up |
| Mass assignment | `StrictSerializer` rejects unknown fields; form values validated against the pinned version's field list |
| SQL injection | ORM only; automation paths are dictionary keys, never column names |
| XSS | escaped rendering; sanitiser for richtext; CSP with nonce |
| CSRF | unchanged; new POSTs go through `apiMutate` |
| Unsafe uploads | existing pipeline; policy ceilings |
| Unsafe URLs | `url` fields https-only; `link` variables built server-side |
| Brute force | throttles + lockout + OTP attempt limits |
| Session attacks | hashed keys, per-session revoke, new-device notice, step-up |
| Sensitive data exposure | scrubbed logs/audit; student-visible field filtering; no code in Delivery |
| Unauthorized exports | re-scope in worker; `data.export` lockable |
| Stale authorization cache | version-keyed cache bumped on commit; test that revocation is visible on the next request |
