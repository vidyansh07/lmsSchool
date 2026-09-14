"""D-130: the manager and the counsellor stand side by side; a manager teaches.

What is pinned:

- a manager, not a counsellor, brings trainers in (the two-capability gap);
- a manager can be given a trainer profile through the API, is then assignable
  to a batch, reaches the teaching routes, and signs off their own daily
  report — the trusted-manager rule — while a trainer still cannot;
- a student cannot be made a trainer by being picked in a search box;
- a counsellor opens a course shell with a usual fee, and the fee comes back
  on the catalogue row.
"""

from __future__ import annotations

import pytest

from apps.accounts.roles import Capability, has_capability
from apps.trainers.models import TrainerProfile

TEACHING_URL = "/api/v1/trainers/teaching-profile/"


@pytest.mark.django_db
def test_only_a_manager_brings_trainers_in(manager_user, counsellor_user):
    assert has_capability(manager_user, Capability.TRAINER_CREATE)
    assert has_capability(manager_user, Capability.TRAINER_UPDATE_ANY)
    assert not has_capability(counsellor_user, Capability.TRAINER_CREATE)
    assert not has_capability(counsellor_user, Capability.TRAINER_UPDATE_ANY)


@pytest.mark.django_db
def test_a_manager_becomes_a_trainer_and_teaches_a_batch(
    api_client_no_csrf, manager_user, batch, trainer_profile
):
    api_client_no_csrf.force_login(manager_user)
    first = api_client_no_csrf.post(TEACHING_URL, {"user_id": str(manager_user.pk)}, format="json")
    assert first.status_code == 200, first.data
    profile_id = first.json()["id"]
    assert TrainerProfile.objects.filter(user=manager_user).count() == 1
    # Idempotent: the second call is the same profile, not a second one.
    again = api_client_no_csrf.post(TEACHING_URL, {"user_id": str(manager_user.pk)}, format="json")
    assert again.json()["id"] == profile_id
    assert TrainerProfile.objects.filter(user=manager_user).count() == 1
    manager_user.refresh_from_db()
    assert manager_user.role == "manager"

    assigned = api_client_no_csrf.post(
        f"/api/v1/batches/{batch.pk}/trainer/", {"trainer_id": profile_id}, format="json"
    )
    assert assigned.status_code == 200, assigned.data
    batch.refresh_from_db()
    assert str(batch.trainer_id) == profile_id

    me = api_client_no_csrf.get("/api/v1/trainers/me/")
    assert me.status_code == 200
    assert me.json()["id"] == profile_id


@pytest.mark.django_db
def test_a_counsellor_cannot_make_anybody_a_trainer(
    api_client_no_csrf, counsellor_user, manager_user
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        TEACHING_URL, {"user_id": str(manager_user.pk)}, format="json"
    )
    assert response.status_code == 403
    assert not TrainerProfile.objects.filter(user=manager_user).exists()


@pytest.mark.django_db
def test_a_student_is_not_made_a_trainer_by_a_search_box(
    api_client_no_csrf, manager_user, student_profile
):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.post(
        TEACHING_URL, {"user_id": str(student_profile.user.pk)}, format="json"
    )
    assert response.status_code == 400
    assert "user_id" in response.json()["error"]["details"]


@pytest.mark.django_db
def test_a_manager_who_teaches_signs_off_their_own_report(manager_user, batch, admin_user):
    from datetime import time

    from apps.dsr.models import DSRStatus
    from apps.dsr.services import review_dsr, start_dsr, submit_dsr
    from apps.sessions.models import ClassSession, SessionStatus
    from apps.trainers.services import ensure_teaching_profile

    profile = ensure_teaching_profile(user=manager_user, actor=manager_user)
    session = ClassSession.objects.create(
        batch=batch,
        session_date=batch.start_date,
        start_time=time(9, 0),
        end_time=time(11, 0),
        status=SessionStatus.COMPLETED,
        trainer=profile,
    )
    dsr = start_dsr(session=session, actor=manager_user)
    submit_dsr(dsr=dsr, actor=manager_user)
    reviewed = review_dsr(dsr=dsr, actor=manager_user, decision=DSRStatus.APPROVED)
    assert reviewed.status == DSRStatus.APPROVED


@pytest.mark.django_db
def test_a_trainer_still_cannot_review_their_own_report(trainer_profile, batch, admin_user):
    from datetime import time

    from apps.common.exceptions import AuthorityError
    from apps.dsr.models import DSRStatus
    from apps.dsr.services import review_dsr, start_dsr, submit_dsr
    from apps.sessions.models import ClassSession, SessionStatus

    session = ClassSession.objects.create(
        batch=batch,
        session_date=batch.start_date,
        start_time=time(9, 0),
        end_time=time(11, 0),
        status=SessionStatus.COMPLETED,
        trainer=trainer_profile,
    )
    dsr = start_dsr(session=session, actor=trainer_profile.user)
    submit_dsr(dsr=dsr, actor=trainer_profile.user)
    with pytest.raises(AuthorityError):
        review_dsr(dsr=dsr, actor=trainer_profile.user, decision=DSRStatus.APPROVED)


@pytest.mark.django_db
def test_a_counsellor_opens_a_course_shell_with_its_usual_fee(
    api_client_no_csrf, counsellor_user, category
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        "/api/v1/courses/",
        {
            "title": "Python Foundations",
            "category": str(category.pk),
            "short_description": "Three months, evenings.",
            "default_fee": "25000",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.json()["default_fee"] == "25000.00"
    listed = api_client_no_csrf.get("/api/v1/courses/").json()["results"]
    assert any(row["default_fee"] == "25000.00" for row in listed)
