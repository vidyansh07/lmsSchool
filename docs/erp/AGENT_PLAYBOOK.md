# Agent playbook — one file instead of ten

Read this instead of re-deriving conventions from scratch every phase.
Every rule and skeleton below is extracted from working code already
committed (`apps/authorization`, `apps/policies`, Phases 1–5) — not
aspirational, real. When in doubt, the actual file beats this summary; this
exists to cut the time spent *finding* the pattern, not to replace reading
the two or three files a phase specifically touches.

## The five rules (from GRASS_LMS_PROJECT_CONTEXT.md, restated once)

1. Business rules in `services.py`. Never in serializers or views.
2. Authorization is a queryset first: `visible_*()`/`manageable_*()`
   functions resolve records, so a guessed id 404s before any permission
   code runs. Never `get_object_or_404(Model.objects, pk=id)` directly on
   an unscoped manager for anything a specific role should not reach.
3. Serializers reject unknown fields (`StrictSerializer`/
   `StrictModelSerializer`) and are scoped by caller — an admin-write
   serializer and a self-service one are different classes.
4. Capabilities, not role checks. `HasCapability` +
   `required_capability`/`capability_map`. New enum member in
   `apps/accounts/roles.py` → `sync_permissions` picks it up automatically
   (never hand-edit seeded `RolePermission` rows).
5. Every state change audited via `apps.audit.services.record()`.

Plus the standing rules: never JWT, never bypass service-layer
authorization, never silently discard invalid input, never expose
soft-deleted rows through normal queries, never `undefined`/`NaN`/`Invalid
Date` to the UI, every migration additive.

## Backend app skeleton

```
apps/<name>/
  __init__.py
  apps.py            # AppConfig, default_auto_field, name, verbose_name
  models.py          # see below
  services.py        # business rules, transaction.atomic, record()
  serializers.py      # StrictSerializer / StrictModelSerializer
  views.py           # HasCapability, extend_schema(responses=...)
  urls.py            # app_name + urlpatterns
  migrations/
```

**models.py** — soft-deletable model:
```python
from apps.common.models import BaseModel, SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers

class ThingQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related("owner").prefetch_related("children")

class Thing(SoftDeleteBaseModel):
    name = models.CharField(max_length=120)
    objects, all_objects = soft_delete_managers(ThingQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["name"], name="thing_name_unique",
                condition=models.Q(deleted_at__isnull=True),  # ALWAYS partial
            ),
        ]
```
Security artifacts that must NEVER be restorable (OTP codes, MFA devices,
recovery codes, sessions) use plain `BaseModel`, not soft-delete — a
"restorable" bypass would be a vulnerability. Disable/revoke there is a
genuine delete or a `revoked_at`/`used_at` flag, not `deleted_at`.

**services.py** pattern (from `apps/policies/services.py`):
```python
@transaction.atomic
def update_policy(*, actor, category, key, value, reason, confirm=None):
    schema = _schema_for(category, key)
    _validate(schema, value)
    if schema.critical and confirm != key:
        raise ApplicationError({"confirm": ["This is a critical setting. Confirm by repeating its key exactly."]})
    row, _ = Policy.objects.update_or_create(category=category, key=key, defaults={"value": value})
    PolicyVersion.objects.create(policy=row, version=row.version, value=value, changed_by=actor, reason=reason)
    forget(f"policy:{category}:{key}")
    record(action=AuditAction.POLICY_UPDATED, actor=actor, resource_type="policy",
           resource_id=str(row.pk), context={"category": category, "key": key, "from": ..., "to": value})
    return row
```
Refusals are typed exceptions (`ApplicationError` 400, `ConflictError` 409,
`AuthorityError` 403) — never a bare `ValueError` or manual `Response(...,
status=400)` inside a service.

**views.py** pattern:
```python
class ThingListCreateView(ListAPIView):
    permission_classes = (HasCapability,)
    capability_map = {"GET": Capability.THING_VIEW_ANY, "POST": Capability.THING_MANAGE}
    serializer_class = ThingSerializer
    queryset = Thing.objects.none()  # satisfies drf-spectacular's schema generation

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Thing.objects.none()
        return visible_things(self.request.user)

    @extend_schema(summary="...", responses={200: ThingSerializer(many=True)}, tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
```
A bare `APIView` with only `POST` still needs `serializer_class` set (even
if unused by that method) or drf-spectacular's `check --deploy` warns —
this bit Phase 2's `LockPermissionView`. Every `extend_schema` needs
`responses=`.

A `ListAPIView`/`ListCreateAPIView` still needs its own `serializer_class`
set even when its `get`/`post` is decorated with
`@extend_schema(responses=...)` — the decorator's `responses=` satisfies
drf-spectacular's *schema-generation* check (so `check --deploy`/
`spectacular --fail-on-warn` stay silent) but does nothing for the
*runtime* call: `ListAPIView.get()` still calls
`self.get_serializer(page, many=True)` internally, which calls
`get_serializer_class()` and raises `AssertionError` at request time if
it's unset. This bit Phase 14's `AutomationRuleListCreateView` — verify
clean, `check --deploy` clean, 3178 tests green, and the endpoint still
500'd on first real staging traffic, because no test in the phase's own
suite ever called `GET` on it through the view layer (every test called
`services.*` directly). Lesson: for any `List*View`/`*ListCreateAPIView`,
confirm `serializer_class` is set by reading the class, not by trusting
`check --deploy`'s silence — and give it at least one real
`client.get(url)`-shaped test, not only a services-layer test.

**Anonymous-POST endpoints** (login, MFA verify, OTP request) MUST inherit
`EnforceCSRFMixin` — DRF only checks CSRF once `SessionAuthentication`
finds a logged-in user, so an `AllowAnyPublic` POST is unprotected by
default. Phase 5's review caught exactly this gap on one endpoint; check
every new anonymous-reachable view for it.

**Secrets** (codes, TOTP secrets, recovery codes, session keys): store only
a hash (`hashlib.sha256`) or, for TOTP, Fernet-encrypted
(`MFA_ENCRYPTION_KEY`, no default in `hardened.py`/`production.py` —
`require_setting` fails closed). Never in an audit `context` dict under
any key name. Never logged. The one response that may carry a secret in
the clear is the single enrolment/generation response; nothing else ever
returns it again.

**Check-then-act races**: any "count then create" (rate limits, uniqueness
outside a DB constraint) needs `select_for_update()` on a row that exists,
or a `pg_advisory_xact_lock()` keyed on the contended value when there is
no row yet (see `apps/accounts/otp.py::_advisory_lock_key`). Phase 4's
review caught exactly this bug in the "first send of the hour" path.

## Frontend skeleton

```
frontend/lib/<name>.ts       # apiFetch/apiMutate client, typed, no 'any'
frontend/types/api.ts        # add the response/request shapes
frontend/lib/capabilities.ts # add new capability names
frontend/lib/labels.ts       # add label/variant maps if there's an enum
frontend/components/<area>/<screen>.tsx
frontend/app/<route>/page.tsx
frontend/tests/unit/<screen>.test.tsx
```
Reuse `components/ui/*` (Dialog, Field, Input, Select, Table, Badge,
Alert, Button) — never a new primitive. Every screen: loading, empty,
error, denied (if capability-gated), success. `frontend/components/roles/
role-builder.tsx` + `app/admin/roles/page.tsx` (Phase 1) is the cleanest
current reference for a full CRUD admin screen; `step-up-dialog.tsx`
(Phase 2/4/5) for a dialog with a mode toggle and step-up retry.

Nav entry: add to both `STAFF_NAV` and `ADMIN_NAV` in
`components/navigation.ts`, same spot as the last similar entry, gated on
the new capability.

## The verify checklist (10 commands, same every phase)

```
cd backend && .venv/bin/ruff format --check apps config tests
cd backend && .venv/bin/ruff check apps config tests
cd backend && export DATABASE_URL=postgres://grras:localdevpassword@127.0.0.1:55433/wt_vision DJANGO_ENV=test DJANGO_SETTINGS_MODULE=config.settings.test && .venv/bin/python manage.py makemigrations --check --dry-run
cd backend && export DATABASE_URL=postgres://grras:localdevpassword@127.0.0.1:55433/wt_vision_b DJANGO_ENV=test DJANGO_SETTINGS_MODULE=config.settings.test && .venv/bin/python -m pytest tests apps/organisation/tests apps/common/tests apps/accounts/tests --ignore=tests/test_smoke.py -q -p no:cacheprovider --no-header -o addopts=""
cd backend && .venv/bin/bandit -c pyproject.toml -r apps config manage.py -q
cd backend && DJANGO_ENV=production DJANGO_SETTINGS_MODULE=config.settings.production DJANGO_SECRET_KEY=<50+ chars> DJANGO_ALLOWED_HOSTS=api.example.com CSRF_TRUSTED_ORIGINS=https://app.example.com CORS_ALLOWED_ORIGINS=https://app.example.com DATABASE_URL=postgres://user:pass@db.example.com:5432/lms CACHE_URL=redis://cache.example.com:6379/0 EMAIL_HOST=smtp.example.com DEFAULT_FROM_EMAIL=no-reply@example.com FRONTEND_BASE_URL=https://app.example.com MFA_ENCRYPTION_KEY=<generated> SENTRY_DSN= .venv/bin/python manage.py check --deploy --fail-level WARNING
cd frontend && npm run lint --silent
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run --silent
```
Postgres: docker container `grras-lms-db-1`, `127.0.0.1:55433`, user
`grras`, password `localdevpassword`. `wt_vision` for iterative work,
`wt_vision_b` for full-suite runs (avoids lock contention if two things
run at once). Never touch `wt_vision_dev` — other sessions use it.

---

# Process notes — going faster without checking less

Measured this session: a phase costs 90–180 minutes of agent wall-clock
(backend + frontend + verify loop + review + finalize) plus 15–40 minutes
of my own follow-up (independent re-check, deploy, smoke test, crawl,
docs). Almost none of that is "thinking slowly" — it's the full test suite
(2800+ backend, 950+ frontend) running three or four times per phase when
once would do, and docs being redone by hand after an agent gets them
half-right.

Rules for every phase from here on:

1. **The full suite runs at most twice inside a workflow**: once in
   Verify's first pass, and again only if a fixer (Verify's or Review's)
   actually touched code after that. If Review finds nothing, Finalize
   does **not** re-run the 10-check list — it just commits the
   already-proven state.
2. **I do not re-run the full suite myself** when Finalize reports
   `committed: true` with a clean status. I do a light spot-check instead
   (migration-drift check, the phase's own new test file, `ruff check`) —
   seconds, not minutes — before merging and deploying. Recovery from a
   transient network error (checking disk state, running the suite myself)
   remains the exception, not the default per-phase step.
3. **Crawl only when a phase ships a new route or nav entry.** Backend-only
   or config-only phases skip it.
4. **Every deploy ends with an explicit `docker compose ps`** confirming
   every service is `Up ... (healthy)` — not just a grep of `deploy.sh`'s
   tail output, which can miss a container stuck in `Created`.
5. **Docs (`FEATURE_STATUS.md` row, checklist row) are written by me from
   the workflow's own final report**, using the row-per-phase template
   already established (14.1–14.6), rather than trusted to an agent's last
   paragraph — this has drifted twice (a stale `IN_PROGRESS`, a missing
   row) and is faster for me to template than to audit and fix after the
   fact.
6. **Reasoning effort scales to risk.** Auth/security/money-adjacent
   phases (done: 1, 2, 4, 5, 6; ahead: 14 automation, 19 communication)
   keep `effort: 'high'` throughout, including a full adversarial Review.
   Mechanical/data-shape phases (soft-delete extension, catalogs, form
   builder scaffolding) can run implementers at `'medium'` and a lighter,
   faster Review pass — still adversarial, just not a 75-tool-call sweep
   over a phase with no new authorization surface.
7. **Backend and Frontend implementers run in parallel, not sequentially,
   when the phase's prompt already pins the exact API contract** (as every
   phase prompt in this programme does — request/response shapes are
   specified up front, not left for the backend agent to invent). The
   frontend agent is told the contract directly instead of "read the
   backend's code first"; any drift is caught by Verify's `tsc`/test pass
   like any other bug, at the cost of one possible fix-loop iteration
   instead of the guaranteed 15–20 minutes sequential wait saves every
   time. Phases where the frontend genuinely cannot be specified until
   backend is written (rare — none so far) stay sequential.
8. **Independent, low-interdependency phases may run concurrently once
   we reach them** (the plan already marks some: Phase 20 export work
   alongside 12–19; Phases 15–18 workspace UIs alongside each other once
   9 lands). This needs separate git worktrees per concurrent phase to
   avoid file-level collisions, merged back sequentially. Not worth the
   setup cost for the current strictly-sequential 7–14 stretch; revisit
   when the plan's own parallel-safe phases arrive.

None of this reduces what gets checked. It removes checking the same
already-true thing a second and third time, and stops big commodity
docs-formatting work from being redelegated when a template is faster and
more reliable.
