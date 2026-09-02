# Authentication

One strategy, used everywhere. There is no second authentication system, and no
endpoint bypasses this one.

---

## 1. How browser authentication works

Session cookies, issued and validated by Django.

```
 browser                                   backend
    │                                         │
    │  GET /api/v1/auth/csrf/                 │
    │────────────────────────────────────────▶│
    │◀────────── Set-Cookie: grras_csrftoken ─│   readable by JS, not a credential
    │                                         │
    │  POST /api/v1/auth/login/               │
    │  X-CSRFToken: <cookie value>            │
    │  { email, password }                    │
    │────────────────────────────────────────▶│   verify → cycle session key
    │◀───── Set-Cookie: grras_sessionid ──────│   HttpOnly, Secure, SameSite=Lax
    │                                         │
    │  every later request carries the        │
    │  session cookie automatically           │
    │────────────────────────────────────────▶│
```

Cookie properties, and why each one is there:

| Cookie | Flags | Purpose |
| --- | --- | --- |
| `grras_sessionid` | `HttpOnly`, `Secure`*, `SameSite=Lax`, 12h sliding | The credential. `HttpOnly` means JavaScript cannot read it, so an XSS bug cannot exfiltrate a session. |
| `grras_csrftoken` | `Secure`*, `SameSite=Lax`, readable | Anti-forgery token. Deliberately readable so the SPA can echo it in `X-CSRFToken`. It is not a credential on its own. |

\* `Secure` everywhere except local development over plain HTTP.

### Why sessions and not JWT

The alternative — a token held in JavaScript-reachable storage — trades away
three properties this system needs:

* **XSS containment.** An `HttpOnly` cookie cannot be read by injected script.
* **Immediate revocation.** Deactivating an account or changing a password takes
  effect on the *next request*. A self-contained JWT stays valid until it
  expires, which is exactly the wrong behaviour when an account is compromised.
* **Simplicity.** No refresh-token rotation, no client-side expiry handling, no
  second code path to get wrong.

The cost is statelessness, which this system does not need.

### Deployment requirement

Because the session cookie is `SameSite=Lax`, the frontend and API must share a
registrable domain in deployed environments — for example `app.grras.example`
and `api.grras.example`. Hosting them on unrelated domains would force
`SameSite=None` and weaken CSRF defence in depth.

---

## 2. How the API authenticates a request

`SessionAuthentication` is the only authentication class configured. Each
request:

1. Django's session middleware decodes `grras_sessionid` and loads the user.
2. DRF's `SessionAuthentication` accepts that user, and — for unsafe methods —
   runs the CSRF check.
3. `IsActiveUser` (the project-wide default permission) requires the user to be
   authenticated **and still active**.
4. The view's declared capability is checked against the role-capability matrix.
5. Object-level rules run for anything owned by a specific person.

Step 3 is what makes deactivation immediate: an existing session belonging to a
deactivated user is rejected on its very next request.

### The CSRF gap this project closes

DRF marks API views `csrf_exempt` and defers the check to session
authentication, which only runs once a session user exists. Endpoints that
accept **anonymous** unsafe requests — login above all — are therefore
unprotected by default, which permits login CSRF (forcing a victim's browser
into an attacker-controlled session).

`apps.common.mixins.EnforceCSRFMixin` closes it, and is applied to every
anonymous POST endpoint: login, password reset request, password reset confirm,
email verification confirm. **Any future endpoint accepting an unauthenticated
unsafe request must use it.**

Both CSRF paths — DRF's own and the mixin's — are normalised by the exception
handler to one code, `csrf_failed`, with the server-side reason stripped out.

---

## 3. Non-browser clients

None exist yet. When a mobile app or a service integration needs access, add a
token authentication class to `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`
alongside the session class. The permission layer is authentication-agnostic, so
no view changes.

That work is deliberately deferred: unused authentication is unreviewed attack
surface.

---

## 4. Logout and invalidation

There are four ways a session stops working. Three are automatic.

| Trigger | Mechanism | Scope |
| --- | --- | --- |
| Sign out | `logout()` flushes the session | This device |
| Sign out everywhere | `POST /auth/logout-all/` deletes every stored session for the user | All devices |
| Password change or reset | Django rotates the session auth hash, invalidating every session signed with the old one | All other devices (change) / all devices (reset) |
| Account deactivation | `IsActiveUser` rejects the next request, **and** stored sessions are deleted | All devices |

`apps.accounts.services.revoke_sessions` performs the explicit deletion and
writes an audit entry, so "signed out everywhere" is a reviewable event rather
than an invisible side effect.

Implementation note: Django's session table is keyed by session key with the
user id inside the encoded payload, so finding one user's sessions means
decoding the non-expired rows. That is fine at this scale. If the session table
grows large, move to a backend that indexes the user id rather than making this
query cleverer.

---

## 5. Expiry

| Item | Lifetime | Rationale |
| --- | --- | --- |
| Session | 12 hours, sliding (`SESSION_SAVE_EVERY_REQUEST`) | Long enough for a working day; an idle session dies. |
| CSRF token | 1 year | Not a credential; rotating it only breaks open tabs. |
| Password reset token | 1 hour (`AUTH_TOKEN_RESET_TTL_HOURS`) | Grants account takeover, so it is short-lived. |
| Email verification token | 3 days (`AUTH_TOKEN_VERIFICATION_TTL_DAYS`) | Much weaker, so a longer window is acceptable. |

There are no refresh tokens: sessions renew by being used, which is what the
sliding expiry does.

---

## 6. Tokens for password reset and verification

`apps.accounts.models.AccountToken` backs both flows.

* **Only a SHA-256 hash is stored.** The raw token exists in the emailed link
  and nowhere else, so reading the database cannot produce account takeover.
  A plain hash is correct here — unlike for a password, the token is 256 bits of
  randomness, so there is nothing to brute-force, and lookup stays one indexed
  query.
* **Single use.** `used_at` is stamped in the same transaction that consumes it.
* **Expiring**, per the table above.
* **Superseding.** Issuing a new token of a purpose invalidates that user's
  outstanding ones, so an older link in an inbox stops working.
* **Purpose-scoped.** A reset token cannot be replayed against the verification
  endpoint.

Unknown, expired and already-used tokens all produce the **same** error
(`invalid_token`). Distinguishing them would tell an attacker whether a guessed
token ever existed.

The raw token is never logged and never written to an audit record.

---

## 7. Account enumeration

Two endpoints could otherwise reveal who has an account. Both are closed:

* **Login** answers 401 with `Invalid credentials.` for a wrong password, an
  unknown address, and an inactive account alike.
* **Password reset request** always answers `202` with the same body, and takes
  the same path, whether or not the address exists. Mail is sent only when it
  does.

Both outcomes are still recorded in the audit log — the *server* knows the
difference; the client never learns it.

---

## 8. Rate limiting

| Scope | Default | Applies to |
| --- | --- | --- |
| `auth` | 10/min per IP | Login, password change, reset request, reset confirm, verification |
| `anon` | 60/min | Other anonymous requests |
| `user` | 600/min | Authenticated requests |

Counters live in the Django cache. Deployed environments **must** set
`CACHE_URL` — the app refuses to start without it — because per-worker counters
would multiply every limit by the worker count.

Client IP resolution honours only as many proxies as `NUM_PROXIES` declares;
trusting the whole `X-Forwarded-For` chain would let a client spoof its address
and defeat both rate limiting and audit attribution.

---

## 9. Where authentication logic lives

| Layer | Responsibility |
| --- | --- |
| `apps/accounts/services.py` | Every rule: credential checks, token issue and consumption, session revocation, audit writes |
| `apps/accounts/views.py` | HTTP shape only — parse, call a service, serialise |
| `apps/common/permissions.py` | Capability and ownership checks |
| `frontend/lib/auth.ts` | Transport only: URLs, CSRF handshake, error mapping |
| `frontend/components/auth-provider.tsx` | Caches "who am I?" for rendering |

No React component performs an authentication or authorization decision. The
frontend's capability list decides what to *show*; the backend decides what is
*allowed*, on every request.
