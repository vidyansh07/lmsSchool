"""Policy management (ERP Phase 3, ADR-04).

- every schema key resolves to its default until something is configured;
- a value is validated against its schema (type, range, choices, the
  `weights` dict's exact component set) — good values are accepted, bad
  ones refused with the field named;
- a critical key needs a fresh step-up and a `confirm` naming the key
  exactly; a non-critical key needs neither;
- every write is versioned, newest first, and a reset does not lose the
  history that came before it;
- a write is visible to a read immediately after it — no stale cache;
- `policy.view` (manager and up) and `policy.manage` (admin and up) are
  enforced separately, and a branch-scoped caller cannot reach another
  centre's override or the institution-wide row;
- a branch override falls back to the global row, then the schema default.
"""

from __future__ import annotations

import pytest

from apps.policies.models import Policy, PolicyVersion
from apps.policies.resolver import policy as resolved_policy
from apps.policies.schemas import POLICY_SCHEMAS
from tests.conftest import TEST_PASSWORD

POLICIES = "/api/v1/policies/"


def _detail(category: str, key: str) -> str:
    return f"{POLICIES}{category}/{key}/"


def _history(category: str, key: str) -> str:
    return f"{POLICIES}{category}/{key}/history/"


def _step_up(client) -> None:
    stepped = client.post("/api/v1/auth/step-up/", {"password": TEST_PASSWORD}, format="json")
    assert stepped.status_code == 204, stepped.json()


# ---------------------------------------------------------------------------
# The schema, resolved
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_schema_key_resolves_to_its_default_until_configured(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(POLICIES).json()
    seen = {(row["category"], row["key"]) for row in body}
    expected = {(category, key) for category, keys in POLICY_SCHEMAS.items() for key in keys}
    assert seen == expected
    for row in body:
        assert row["is_default"] is True
        assert row["value"] == row["default"]
        assert row["version"] == 0


@pytest.mark.django_db
def test_category_filter_narrows_the_list(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(POLICIES, {"category": "session"}).json()
    assert {row["key"] for row in body} == {"max_age_hours", "idle_minutes"}
    assert {row["category"] for row in body} == {"session"}


@pytest.mark.django_db
def test_unknown_category_filter_is_refused(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    refused = api_client_no_csrf.get(POLICIES, {"category": "nonsense"})
    assert refused.status_code == 400


@pytest.mark.django_db
def test_unknown_key_is_not_found(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    assert api_client_no_csrf.get(_detail("session", "nonsense")).status_code == 404
    assert api_client_no_csrf.get(_detail("nonsense", "nonsense")).status_code == 404


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_value_within_the_schema_is_accepted(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    ok = api_client_no_csrf.put(
        _detail("authentication", "lockout_after"),
        {"value": 8, "reason": "Tighten after a phishing attempt."},
        format="json",
    )
    assert ok.status_code == 200, ok.json()
    assert ok.json()["value"] == 8
    assert ok.json()["is_default"] is False
    assert ok.json()["version"] == 1


@pytest.mark.parametrize(
    ("category", "key", "value"),
    [
        ("authentication", "lockout_after", 1),  # below min (3)
        ("authentication", "lockout_after", "ten"),  # wrong type
        ("session", "idle_minutes", -5),  # below min (0)
        ("communication", "guardian_alerts", "yes"),  # not a boolean
        ("notification", "digest_frequency", "hourly"),  # not one of the choices
        ("performance", "weights", {"attendance": 1}),  # missing components
        (
            "performance",
            "weights",
            {
                **dict.fromkeys(
                    ("attendance", "assessment", "assignments", "projects", "progress"), 1
                ),
                "extra": 1,
            },
        ),
        ("risk", "risk_attendance_percent", "not-a-number"),
    ],
)
@pytest.mark.django_db
def test_a_value_outside_the_schema_is_refused(
    api_client_no_csrf, admin_user, category, key, value
):
    api_client_no_csrf.force_login(admin_user)
    refused = api_client_no_csrf.put(
        _detail(category, key), {"value": value, "reason": "trying something"}, format="json"
    )
    assert refused.status_code == 400, refused.json()
    assert Policy.objects.filter(category=category, key=key).count() == 0


@pytest.mark.django_db
def test_the_weights_dict_accepts_exactly_its_five_components(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    ok = api_client_no_csrf.put(
        _detail("performance", "weights"),
        {
            "value": {
                "attendance": 2,
                "assessment": 1,
                "assignments": 1,
                "projects": 1,
                "progress": 1,
            },
            "reason": "Weight attendance more heavily.",
        },
        format="json",
    )
    assert ok.status_code == 200, ok.json()
    assert ok.json()["value"]["attendance"] == "2"


@pytest.mark.django_db
def test_a_reason_is_required(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    refused = api_client_no_csrf.put(
        _detail("session", "idle_minutes"), {"value": 5}, format="json"
    )
    assert refused.status_code == 400


# ---------------------------------------------------------------------------
# Critical keys: step-up and confirm
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_critical_key_needs_a_fresh_step_up(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    refused = api_client_no_csrf.put(
        _detail("password", "min_length"),
        {"value": 12, "reason": "Raise the floor.", "confirm": "min_length"},
        format="json",
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "step_up_required"
    assert Policy.objects.filter(category="password", key="min_length").count() == 0


@pytest.mark.django_db
def test_a_critical_key_needs_confirm_naming_the_key(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    _step_up(api_client_no_csrf)

    missing = api_client_no_csrf.put(
        _detail("password", "min_length"),
        {"value": 12, "reason": "Raise the floor."},
        format="json",
    )
    assert missing.status_code == 400
    assert "confirm" in missing.json()["error"]["details"]

    wrong = api_client_no_csrf.put(
        _detail("password", "min_length"),
        {"value": 12, "reason": "Raise the floor.", "confirm": "history_count"},
        format="json",
    )
    assert wrong.status_code == 400

    correct = api_client_no_csrf.put(
        _detail("password", "min_length"),
        {"value": 12, "reason": "Raise the floor.", "confirm": "min_length"},
        format="json",
    )
    assert correct.status_code == 200, correct.json()
    assert correct.json()["value"] == 12


@pytest.mark.django_db
def test_a_non_critical_key_needs_neither_step_up_nor_confirm(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    ok = api_client_no_csrf.put(
        _detail("export", "retention_days"),
        {"value": 30, "reason": "Give exports more time."},
        format="json",
    )
    assert ok.status_code == 200, ok.json()


@pytest.mark.django_db
def test_resetting_a_critical_key_also_needs_a_fresh_step_up(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    _step_up(api_client_no_csrf)
    api_client_no_csrf.put(
        _detail("password", "min_length"),
        {"value": 12, "reason": "Raise the floor.", "confirm": "min_length"},
        format="json",
    )
    # Freshness lasts only until the session's step-up window; simulate its
    # expiry the same way a stale-but-signed-in session would see it.
    session = api_client_no_csrf.session
    del session["step_up_at"]
    session.save()
    refused = api_client_no_csrf.delete(_detail("password", "min_length"))
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "step_up_required"


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_every_write_is_versioned_newest_first(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.put(
        _detail("export", "retention_days"), {"value": 21, "reason": "First change."}, format="json"
    )
    api_client_no_csrf.put(
        _detail("export", "retention_days"),
        {"value": 30, "reason": "Second change."},
        format="json",
    )
    history = api_client_no_csrf.get(_history("export", "retention_days")).json()
    versions = [(row["version"], row["value"], row["reason"]) for row in history["results"]]
    assert versions == [(2, 30, "Second change."), (1, 21, "First change.")]


@pytest.mark.django_db
def test_a_reset_does_not_lose_the_history_that_came_before_it(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.put(
        _detail("export", "retention_days"), {"value": 21, "reason": "First change."}, format="json"
    )
    reset = api_client_no_csrf.delete(_detail("export", "retention_days"))
    assert reset.status_code == 200
    assert reset.json()["is_default"] is True

    api_client_no_csrf.put(
        _detail("export", "retention_days"), {"value": 45, "reason": "Reconfigured."}, format="json"
    )
    history = api_client_no_csrf.get(_history("export", "retention_days")).json()
    reasons = [row["reason"] for row in history["results"]]
    assert reasons == ["Reconfigured.", "First change."]


@pytest.mark.django_db
def test_resetting_something_never_configured_is_a_no_op(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    ok = api_client_no_csrf.delete(_detail("export", "retention_days"))
    assert ok.status_code == 200
    assert ok.json()["is_default"] is True
    assert PolicyVersion.objects.count() == 0


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_read_right_after_a_write_sees_the_new_value(api_client_no_csrf, admin_user):
    assert resolved_policy("communication", "guardian_alerts") is False
    api_client_no_csrf.force_login(admin_user)
    updated = api_client_no_csrf.put(
        _detail("communication", "guardian_alerts"),
        {"value": True, "reason": "Enable alerts."},
        format="json",
    )
    assert updated.status_code == 200, updated.json()
    # The resolver — not just the view's own response — must not still be
    # holding the value it cached before this write.
    assert resolved_policy("communication", "guardian_alerts") is True

    fetched = api_client_no_csrf.get(_detail("communication", "guardian_alerts")).json()
    assert fetched["value"] is True


@pytest.mark.django_db
def test_a_no_op_write_changes_nothing_and_writes_no_history(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    api_client_no_csrf.put(
        _detail("export", "retention_days"), {"value": 21, "reason": "First change."}, format="json"
    )
    same = api_client_no_csrf.put(
        _detail("export", "retention_days"),
        {"value": 21, "reason": "Repeat the same value."},
        format="json",
    )
    assert same.status_code == 200
    assert same.json()["version"] == 1
    assert PolicyVersion.objects.filter(policy__key="retention_days").count() == 1


# ---------------------------------------------------------------------------
# Capability gating
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_policy_view_is_held_by_manager_and_up_not_counsellor_trainer_student(
    api_client_no_csrf, admin_user, manager_user, counsellor_user, trainer, student
):
    for user, expected in (
        (admin_user, 200),
        (manager_user, 200),
        (counsellor_user, 403),
        (trainer, 403),
        (student, 403),
    ):
        api_client_no_csrf.force_login(user)
        assert api_client_no_csrf.get(POLICIES).status_code == expected


@pytest.mark.django_db
def test_policy_manage_is_held_by_admin_and_up_only(
    api_client_no_csrf, admin_user, manager_user, unbounded_superadmin
):
    for user, expected in ((manager_user, 403), (admin_user, 200), (unbounded_superadmin, 200)):
        api_client_no_csrf.force_login(user)
        response = api_client_no_csrf.put(
            _detail("export", "retention_days"),
            {"value": 20, "reason": "Vary by role."},
            format="json",
        )
        assert response.status_code == expected, response.json()

    api_client_no_csrf.force_login(manager_user)
    assert api_client_no_csrf.delete(_detail("export", "retention_days")).status_code == 403


# ---------------------------------------------------------------------------
# Branch override, falling back to global, then the schema default
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_branch_override_falls_back_to_global_then_the_default(
    api_client_no_csrf, admin_user, branch, other_branch
):
    api_client_no_csrf.force_login(admin_user)
    assert resolved_policy("session", "idle_minutes") == 0

    global_write = api_client_no_csrf.put(
        _detail("session", "idle_minutes"),
        {"value": 15, "reason": "Institution-wide idle timeout."},
        format="json",
    )
    assert global_write.status_code == 200
    assert resolved_policy("session", "idle_minutes") == 15
    assert resolved_policy("session", "idle_minutes", branch=branch) == 15  # falls back to global

    branch_write = api_client_no_csrf.put(
        _detail("session", "idle_minutes"),
        {"value": 30, "branch": str(branch.id), "reason": "This centre is slower to lock."},
        format="json",
    )
    assert branch_write.status_code == 200
    assert resolved_policy("session", "idle_minutes", branch=branch) == 30
    assert (
        resolved_policy("session", "idle_minutes", branch=other_branch) == 15
    )  # still the global value
    assert resolved_policy("session", "idle_minutes") == 15  # global untouched by the override

    reset = api_client_no_csrf.delete(f"{_detail('session', 'idle_minutes')}?branch={branch.id}")
    assert reset.status_code == 200
    assert (
        resolved_policy("session", "idle_minutes", branch=branch) == 15
    )  # back to falling through


@pytest.mark.django_db
def test_a_branch_scoped_manager_can_only_reach_their_own_centre(
    api_client_no_csrf, manager_user, branch, other_branch
):
    api_client_no_csrf.force_login(manager_user)
    own = api_client_no_csrf.get(_detail("session", "idle_minutes"), {"branch": str(branch.id)})
    assert own.status_code == 200

    other = api_client_no_csrf.get(
        _detail("session", "idle_minutes"), {"branch": str(other_branch.id)}
    )
    assert other.status_code == 403

    bad = api_client_no_csrf.get(_detail("session", "idle_minutes"), {"branch": "not-a-uuid"})
    assert bad.status_code == 400

    missing = api_client_no_csrf.get(
        _detail("session", "idle_minutes"), {"branch": "00000000-0000-0000-0000-000000000000"}
    )
    assert missing.status_code == 404
