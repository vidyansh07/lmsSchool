"""`POST /users/bulk/`: resend invitations to, or move, many accounts at once.

Every account still goes through the single-account service — the authority
ladder, the centre rule, the audit entry — and an account a rule refuses is
skipped with the reason while the rest carry on.
"""

from __future__ import annotations

import pytest

from apps.accounts.models import User, UserRole
from apps.audit.models import AuditAction, AuditLog

URL = "/api/v1/users/bulk/"


def _invited(user) -> bool:
    return AuditLog.objects.filter(
        action=AuditAction.EMAIL_VERIFICATION_REQUESTED, resource_id=str(user.pk)
    ).exists()


def _make(email, role, branch, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password=None,
        first_name=email.split("@")[0],
        role=role,
        branch=branch,
        **extra,
    )


@pytest.mark.django_db
def test_resending_invitations_skips_who_cannot_or_need_not_receive_one(
    api_client_no_csrf, admin_user, branch
):
    pending = _make("pending@example.test", UserRole.COUNSELLOR, branch)
    accepted = _make("accepted@example.test", UserRole.COUNSELLOR, branch, is_email_verified=True)
    dormant = _make("dormant@example.test", UserRole.MANAGER, branch, is_active=False)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        URL,
        {
            "action": "resend_invitation",
            "ids": [str(user.pk) for user in (pending, accepted, dormant, admin_user)],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 4
    assert body["done"] == 1
    reasons = {row["label"]: row["reason"] for row in body["skipped"]}
    assert "already accepted" in reasons["accepted"]
    assert "inactive" in reasons["dormant"]
    assert "your own account" in reasons["Amy Admin"]
    assert _invited(pending)
    assert not _invited(accepted)


@pytest.mark.django_db
def test_every_account_matching_the_filter(api_client_no_csrf, admin_user, branch):
    first = _make("c1@example.test", UserRole.COUNSELLOR, branch)
    second = _make("c2@example.test", UserRole.COUNSELLOR, branch)
    manager = _make("m1@example.test", UserRole.MANAGER, branch)

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        URL,
        {"action": "resend_invitation", "filters": {"role": "counsellor", "search": ""}},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert response.json()["done"] == 2
    assert _invited(first) and _invited(second)
    assert not _invited(manager)


@pytest.mark.django_db
def test_an_id_that_names_nothing_visible_is_reported_not_acted_on(
    api_client_no_csrf, admin_user, branch
):
    import uuid

    local = _make("local@example.test", UserRole.COUNSELLOR, branch)
    forged = str(uuid.uuid4())
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        URL, {"action": "resend_invitation", "ids": [str(local.pk), forged]}, format="json"
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 2
    assert body["done"] == 1
    assert body["skipped"][0]["id"] == forged
    assert "Not found" in body["skipped"][0]["reason"]


@pytest.mark.django_db
def test_moving_accounts_to_a_centre(
    api_client_no_csrf, admin_user, manager_user, counsellor_user, student_profile, other_branch
):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        URL,
        {
            "action": "move_centre",
            "branch_id": str(other_branch.pk),
            "reason": "Opening Pune.",
            "ids": [
                str(manager_user.pk),
                str(counsellor_user.pk),
                str(student_profile.user.pk),
                str(admin_user.pk),
            ],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["done"] == 2
    reasons = [row["reason"] for row in body["skipped"]]
    assert any("transfer their class" in reason for reason in reasons)
    assert any("your own account" in reason for reason in reasons)
    manager_user.refresh_from_db()
    counsellor_user.refresh_from_db()
    assert manager_user.branch_id == other_branch.pk
    assert counsellor_user.branch_id == other_branch.pk
    assert AuditLog.objects.filter(
        action=AuditAction.USER_BRANCH_CHANGED, resource_id=str(manager_user.pk)
    ).exists()


@pytest.mark.django_db
def test_a_move_needs_a_centre_and_a_reason(api_client_no_csrf, admin_user, manager_user):
    api_client_no_csrf.force_login(admin_user)
    no_reason = api_client_no_csrf.post(
        URL,
        {
            "action": "move_centre",
            "branch_id": str(manager_user.branch_id),
            "ids": [str(manager_user.pk)],
        },
        format="json",
    )
    assert no_reason.status_code == 400
    assert "reason" in str(no_reason.json())

    no_branch = api_client_no_csrf.post(
        URL, {"action": "move_centre", "reason": "x", "ids": [str(manager_user.pk)]}, format="json"
    )
    assert no_branch.status_code == 400


@pytest.mark.django_db
def test_the_authority_ladder_still_applies_per_account(
    api_client_no_csrf, admin_user, unbounded_superadmin, counsellor_user, other_branch
):
    """An administrator who may move accounts still cannot move a superadmin;
    that one is skipped with the reason and the others move."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        URL,
        {
            "action": "move_centre",
            "branch_id": str(other_branch.pk),
            "reason": "Tidy-up.",
            "ids": [str(unbounded_superadmin.pk), str(counsellor_user.pk)],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["done"] == 1
    assert "authority" in body["skipped"][0]["reason"]
    previous = unbounded_superadmin.branch_id
    unbounded_superadmin.refresh_from_db()
    assert unbounded_superadmin.branch_id == previous


@pytest.mark.django_db
def test_a_manager_who_only_reads_accounts_is_refused(
    api_client_no_csrf, manager_user, counsellor_user
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        URL, {"action": "resend_invitation", "ids": [str(counsellor_user.pk)]}, format="json"
    )
    assert response.status_code == 403
    assert not _invited(counsellor_user)


@pytest.mark.django_db
def test_somebody_without_the_right_is_refused(api_client_no_csrf, counsellor_user, manager_user):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        URL, {"action": "resend_invitation", "ids": [str(manager_user.pk)]}, format="json"
    )
    assert response.status_code == 403
    assert not _invited(manager_user)


@pytest.mark.django_db
def test_ids_or_filters_but_not_neither(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    assert (
        api_client_no_csrf.post(URL, {"action": "resend_invitation"}, format="json").status_code
        == 400
    )


@pytest.mark.django_db
def test_too_broad_a_filter_is_refused(api_client_no_csrf, admin_user, branch, monkeypatch):
    from apps.common import bulk

    monkeypatch.setattr(bulk, "MAX_BULK_TARGETS", 1)
    _make("a@example.test", UserRole.COUNSELLOR, branch)
    _make("b@example.test", UserRole.COUNSELLOR, branch)
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        URL, {"action": "resend_invitation", "filters": {"role": "counsellor"}}, format="json"
    )
    assert response.status_code == 400
    assert "Narrow it" in str(response.json())


TRAINERS_URL = "/api/v1/trainers/bulk/"


@pytest.mark.django_db
def test_resending_trainer_invitations_from_the_trainers_hub(
    api_client_no_csrf, admin_user, trainer_profile, trainer_profile_two
):
    """The hub works in trainer ids and the hub's own filters; the rule is the
    accounts list's."""
    trainer_profile.user.is_email_verified = False
    trainer_profile.user.save(update_fields=["is_email_verified"])
    trainer_profile_two.user.is_email_verified = True
    trainer_profile_two.user.save(update_fields=["is_email_verified"])

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        TRAINERS_URL,
        {
            "action": "resend_invitation",
            "ids": [str(trainer_profile.pk), str(trainer_profile_two.pk)],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["done"] == 1
    assert "already accepted" in body["skipped"][0]["reason"]
    assert _invited(trainer_profile.user)

    by_filter = api_client_no_csrf.post(
        TRAINERS_URL,
        {"action": "resend_invitation", "filters": {"search": trainer_profile.trainer_id}},
        format="json",
    )
    assert by_filter.json()["total"] == 1


@pytest.mark.django_db
def test_a_manager_cannot_resend_trainer_invitations(
    api_client_no_csrf, manager_user, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        TRAINERS_URL,
        {"action": "resend_invitation", "ids": [str(trainer_profile.pk)]},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_resending_student_invitations_from_the_students_list(
    api_client_no_csrf, admin_user, student_profile, other_student_profile, manager_user
):
    other_student_profile.user.is_email_verified = True
    other_student_profile.user.save(update_fields=["is_email_verified"])
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        "/api/v1/students/bulk/",
        {"action": "resend_invitation", "filters": {"search": "Learner"}},
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == 2
    assert body["done"] == (0 if student_profile.user.is_email_verified else 1)

    api_client_no_csrf.force_login(manager_user)
    refused = api_client_no_csrf.post(
        "/api/v1/students/bulk/",
        {"action": "resend_invitation", "ids": [str(student_profile.pk)]},
        format="json",
    )
    assert refused.status_code == 403
