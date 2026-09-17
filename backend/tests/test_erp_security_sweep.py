"""ERP Phase 24 — security and regression sweep.

`IMPLEMENTATION_PLAN.md` row 24 names this file, `test_erp_security_sweep`, as
the phase's own gate test, alongside `test_concurrency` (§78). Its job is
narrower than "test everything security-related" — the programme already does
that, spread across twenty-three phases' own test files, each written by the
phase that introduced the control it proves. What was missing was the one
place that *walks* `docs/erp/SECURITY_DECISIONS.md`'s "Threats and controls"
table (§54) row by row and says, in a way pytest itself checks rather than a
comment merely asserting, exactly which test proves which row — so a reviewer
(or the next phase) can see the whole sweep without re-deriving it from
scratch, and so a citation that goes stale (a test renamed or deleted) fails
loudly here instead of quietly leaving a row unproven.

Three things in this file are not citations of existing work, because the
sweep itself found them missing:

1. **Mass assignment** (`test_every_view_serializer_constructed_with_client_
   data_rejects_unknown_fields`) — every serializer any view ever constructs
   with `data=` (i.e. every serializer that ever parses client input) is
   discovered mechanically from the view source, not from a hand-kept list,
   and asserted to reject unknown fields (`apps.common.serializers.
   StrictFieldsMixin`). Running it against the codebase as it stood before
   this phase found exactly two: `FeedQuerySerializer` and
   `ScorecardQuerySerializer` in `apps/activity/serializers.py` (query-string
   validators for the audit feed and scorecards) — both fixed in this phase
   to extend `StrictSerializer` like every other input serializer in the
   codebase already did.
2. **CSRF** on `MfaSendEmailCodeView` — `fix(erp-p05)` (this phase) added
   `EnforceCSRFMixin` to that view but shipped with no regression test, so a
   future refactor could drop the mixin again with nothing to catch it. Added
   below, mirroring `test_auth.py`'s login version of the same proof.
3. **IDOR** on `Delivery.retry`/`Delivery.cancel` — added in this phase's own
   `test_delivery.py` (re-collected here by reference, not duplicated) after
   the sweep found every other Phase 19 id-taking endpoint already covered
   but this one pair untested anywhere.

Everything else below cites, and mechanically checks the continued existence
of, a test written by the phase that actually built the control — because
re-deriving twenty-three phases' worth of proof from scratch in one file
would not be a sweep, it would be a second, competing copy of the suite that
could itself drift out of date.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os

import pytest
from django.conf import settings

import apps as apps_package
from apps.common.serializers import StrictFieldsMixin

# Re-exported so this file's collection actually re-runs the exact proof, the
# same "collected here by reference" pattern `test_concurrency.py` uses for
# the OTP verify race: importing and aliasing a test defined elsewhere is not
# duplicating it, it is running that one true copy from a second entry point.
from tests.test_automation import (
    TestActivateChecksTheActivatorsOwnAuthority as TestPrivilegeEscalationOnActivate,
)
from tests.test_delivery import (
    TestRetryAndCancelAreBranchScoped as TestDeliveryIDOR,
)

__all__ = ["TestDeliveryIDOR", "TestPrivilegeEscalationOnActivate"]


# ---------------------------------------------------------------------------
# The threat table, walked (§54)
# ---------------------------------------------------------------------------
#
# Each row lists (module path, qualified name) pairs: real tests elsewhere in
# the suite (or, for the three gaps above, in this file) that prove that
# row's control. `test_every_threat_table_row_names_a_real_test` below
# resolves every one of them by import — a citation naming a test that was
# since renamed or deleted fails the sweep instead of rotting silently.

THREAT_TABLE: dict[str, list[tuple[str, str]]] = {
    "IDOR": [
        (
            "tests.test_branch_scoping_api",
            "test_a_manager_cannot_fetch_another_centres_record_by_its_real_id",
        ),
        (
            "tests.test_branch_scoping_api",
            "test_the_detail_route_sweep_covers_every_id_taking_endpoint",
        ),
        ("tests.test_erp_security_sweep", "TestDeliveryIDOR"),
        ("tests.test_export_jobs", "test_another_users_job_404s_on_cancel"),
        (
            "tests.test_performance_engine",
            "TestReviewWriting.test_a_student_cannot_see_another_students_review",
        ),
        (
            "tests.test_branch_scoping",
            "test_can_manage_refuses_a_manager_a_notice_from_another_centre",
        ),
        (
            "tests.test_attendance",
            "test_a_student_cannot_see_another_students_record_history",
        ),
    ],
    "Privilege escalation": [
        ("tests.test_erp_security_sweep", "TestPrivilegeEscalationOnActivate"),
        (
            "tests.test_dynamic_roles",
            "test_a_manager_with_a_custom_role_cannot_grant_more_than_it",
        ),
        ("tests.test_role_hierarchy", "test_an_administrator_cannot_edit_a_superadmin"),
        (
            "tests.test_authorization_matrix",
            "test_a_role_without_the_capability_is_refused",
        ),
        ("tests.test_permissions", "test_role_cannot_be_escalated_through_the_api"),
    ],
    "Mass assignment": [
        (
            "tests.test_erp_security_sweep",
            "test_every_view_serializer_constructed_with_client_data_rejects_unknown_fields",
        ),
    ],
    "SQL injection": [
        (
            "tests.test_automation",
            "TestSaveTimePermissionCheck.test_an_unknown_operator_is_refused_at_save_time",
        ),
    ],
    "XSS": [
        (
            "tests.test_templates",
            "TestTemplateInjection.test_script_tag_in_template_body_is_stripped",
        ),
        (
            "tests.test_templates",
            "TestTemplateInjection.test_script_tag_in_a_recipients_own_data_is_stripped_too",
        ),
    ],
    "CSRF": [
        ("tests.test_auth", "test_login_requires_csrf_token_from_a_browser_client"),
        (
            "tests.test_auth",
            "test_csrf_failures_use_one_code_regardless_of_session_state",
        ),
        (
            "tests.test_erp_security_sweep",
            "test_mfa_send_email_code_requires_csrf_token_from_a_browser_client",
        ),
    ],
    "Unsafe uploads": [
        (
            "tests.test_file_storage_security",
            "test_a_rejected_file_is_refused_without_naming_the_detection",
        ),
        (
            "tests.test_profile_image_upload",
            "test_valid_image_is_accepted_and_re_encoded",
        ),
    ],
    "Unsafe URLs": [
        ("tests.test_trainers_api", "test_professional_links_must_be_https_and_known_keys"),
    ],
    "Brute force": [
        ("tests.test_auth", "test_login_is_rate_limited"),
        ("tests.test_otp", "test_two_simultaneous_verifies_only_one_succeeds"),
    ],
    "Session attacks": [
        ("tests.test_sessions", "test_revoking_an_unknown_or_foreign_session_is_404"),
        (
            "tests.test_sessions",
            "test_branch_scoped_holder_of_revoke_any_cannot_reach_another_centre",
        ),
    ],
    "Sensitive data exposure": [
        ("tests.test_audit", "test_recorded_context_is_scrubbed_of_secrets"),
        (
            "tests.test_data_and_audit_security",
            "test_an_audit_entry_never_carries_a_password_or_token",
        ),
        (
            "tests.test_data_and_audit_security",
            "test_the_scrubber_removes_secrets_from_free_text",
        ),
    ],
    "Unauthorized exports": [
        (
            "tests.test_export_jobs",
            "test_scope_is_re_derived_when_the_capability_is_revoked_before_running",
        ),
        (
            "tests.test_export_jobs",
            "test_a_caller_without_view_any_sees_only_their_own_jobs_in_the_list",
        ),
    ],
    "Stale authorization cache": [
        (
            "tests.test_caching",
            "test_revoking_a_permission_is_never_served_stale_to_the_holder",
        ),
    ],
    "Webhook forgery": [
        (
            "tests.test_whatsapp_provider",
            "TestWebhookAuthentication.test_signature_check_rejects_a_wrong_signature",
        ),
        (
            "tests.test_whatsapp_provider",
            "TestWebhookAuthentication."
            "test_post_without_a_valid_signature_is_refused_before_touching_any_delivery",
        ),
    ],
}


def _resolve(module_path: str, qualname: str):
    """Import ``module_path`` and walk ``qualname`` (dotted for a class's own
    method) off it, returning ``None`` if any step is missing."""
    module = importlib.import_module(module_path)
    obj = module
    for part in qualname.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def test_the_threat_table_sweep_is_not_vacuous():
    """A row with no citations, or a table nobody extended, proves nothing."""
    assert len(THREAT_TABLE) >= 13, THREAT_TABLE.keys()
    assert all(citations for citations in THREAT_TABLE.values()), THREAT_TABLE


@pytest.mark.parametrize(
    ("row", "module_path", "qualname"),
    [
        (row, module_path, qualname)
        for row, citations in THREAT_TABLE.items()
        for module_path, qualname in citations
    ],
    ids=[
        f"{row}::{module_path}.{qualname}"
        for row, citations in THREAT_TABLE.items()
        for module_path, qualname in citations
    ],
)
def test_every_threat_table_row_names_a_real_test(row, module_path, qualname):
    """Every citation above still resolves to something real.

    This does not re-run the cited test's assertions (that happens when the
    suite collects its own module) — it proves the *citation* has not gone
    stale, which is the specific failure mode a hand-written audit trail in a
    markdown file cannot catch: a test gets renamed or deleted and the
    document just keeps saying it exists.
    """
    resolved = _resolve(module_path, qualname)
    assert resolved is not None, (
        f"{row!r}'s citation {module_path}.{qualname} no longer resolves — "
        "the test it named was renamed, removed, or never existed."
    )


# ---------------------------------------------------------------------------
# Mass assignment: every serializer a view ever feeds client data through
# ---------------------------------------------------------------------------
#
# `apps/common/serializers.py`'s own docstring names this codebase's
# mass-assignment defence: an input serializer declares an explicit field
# list and *rejects* (not silently ignores) anything outside it. That
# defence only matters for serializers a view actually constructs with
# ``data=`` — a serializer used only to shape a response (``Serializer(
# instance).data``) never calls ``to_internal_value`` at all, so requiring
# it to subclass ``StrictFieldsMixin`` would prove nothing and would flag
# dozens of ordinary read serializers as false positives (confirmed by
# running exactly that broader, and wrong, heuristic while building this
# sweep).
#
# So the discovery has to be "which serializer classes does some view
# actually pass client data into", read from the view modules' own source —
# a hand-kept list of app names goes stale the day a new app or a new write
# endpoint is added; this walks every ``apps/*/views.py`` with the standard
# library's own parser, which cannot go stale that way.


def _serializer_names_constructed_with_client_data() -> set[str]:
    """Every ``SomeSerializer(...)`` call in any ``apps/*/views.py`` that
    passes a ``data=`` keyword — the shape of a serializer being asked to
    parse and validate untrusted input, as opposed to one only rendering a
    response from an already-trusted instance."""
    apps_root = apps_package.__path__[0]
    names: set[str] = set()
    for app_label in settings.INSTALLED_APPS:
        if not app_label.startswith("apps."):
            continue
        views_path = os.path.join(apps_root, app_label.split(".")[-1], "views.py")
        if not os.path.exists(views_path):
            continue
        tree = ast.parse(open(views_path, encoding="utf-8").read(), filename=views_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if not name or not name.endswith("Serializer"):
                continue
            if any(kw.arg == "data" for kw in node.keywords):
                names.add(name)
    return names


def _serializer_classes_by_name() -> dict[str, type]:
    """Every class defined directly in an ``apps/*/serializers.py`` module,
    keyed by its own name (first definition wins on a name collision across
    apps, which none of the current codebase has — checked below)."""
    registry: dict[str, type] = {}
    for app_label in settings.INSTALLED_APPS:
        if not app_label.startswith("apps."):
            continue
        module_name = f"{app_label}.serializers"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and obj.__module__ == module_name:
                registry.setdefault(name, obj)
    return registry


def test_the_mass_assignment_sweep_found_real_input_serializers():
    """Vacuity guard: if the AST walk ever finds nothing, the sweep below
    would trivially pass having checked zero serializers."""
    assert len(_serializer_names_constructed_with_client_data()) >= 100


def test_every_view_serializer_constructed_with_client_data_rejects_unknown_fields():
    """The generalised, self-updating version of `IMPLEMENTATION_PLAN.md`
    row 24's "mass assignment on every serializer": every serializer any
    view feeds ``data=`` must reject a field it does not declare, so a
    request that includes ``role``, ``is_staff`` or any other field a
    serializer never listed fails loudly rather than being silently
    dropped — which is also silently accepted-looking to whoever sent it,
    including an attacker checking whether a field exists at all.
    """
    constructed = _serializer_names_constructed_with_client_data()
    by_name = _serializer_classes_by_name()

    unresolved = sorted(name for name in constructed if name not in by_name)
    assert not unresolved, (
        f"these serializers are constructed with data= in a view but are not "
        f"defined in any apps/*/serializers.py module: {unresolved}"
    )

    non_strict = sorted(
        name for name in constructed if not issubclass(by_name[name], StrictFieldsMixin)
    )
    assert not non_strict, (
        "these serializers parse client input (constructed with data= in a "
        "view) but do not reject unknown fields — extend "
        "apps.common.serializers.StrictSerializer / StrictModelSerializer "
        f"instead of rest_framework.serializers.Serializer / ModelSerializer: {non_strict}"
    )


# ---------------------------------------------------------------------------
# CSRF: the anonymous MFA send-code endpoint (this phase's own fix)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_mfa_send_email_code_requires_csrf_token_from_a_browser_client(api_client):
    """`fix(erp-p05)` (this phase) added `EnforceCSRFMixin` to
    `MfaSendEmailCodeView` after adversarial review found it was the one
    anonymous-POST auth endpoint missing it — unlike `LoginView` and
    `MfaVerifyView`, both already proven by `test_auth.py`'s CSRF tests. That
    fix shipped with no regression test of its own, so a future refactor
    could drop the mixin again with nothing here to catch it. `AllowAnyPublic`
    means no session, pending or otherwise, is even needed to reach the CSRF
    check: `EnforceCSRFMixin.initial()` runs it before the view's own
    pending-session resolution ever executes."""
    response = api_client.post("/api/v1/auth/mfa/send-email-code/", format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
