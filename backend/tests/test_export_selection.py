"""Exporting the rows somebody ticked, not only the rows a filter matches.

The ids go up once (`POST /reports/selections/`) and the export, its count and
a queued job carry a short token instead, because a request line full of ids
does not fit through gunicorn. The token narrows inside the caller's visible
set; it never widens it.
"""

from __future__ import annotations

import pytest

from apps.reporting.selection import MAX_SELECTED

SELECTIONS_URL = "/api/v1/reports/selections/"


def _select(client, ids) -> str:
    response = client.post(SELECTIONS_URL, {"ids": [str(i) for i in ids]}, format="json")
    assert response.status_code == 201, response.content
    return response.json()["selection"]


def _count(client, key: str, token: str) -> int:
    response = client.get(f"/api/v1/reports/{key}/count/?selection={token}")
    assert response.status_code == 200, response.content
    return response.json()["rows"]


@pytest.mark.django_db
def test_an_export_of_ticked_students_has_only_those_rows(
    api_client_no_csrf, admin_user, student_profile, other_student_profile
):
    api_client_no_csrf.force_login(admin_user)
    token = _select(api_client_no_csrf, [student_profile.pk, student_profile.pk])
    assert _count(api_client_no_csrf, "students", token) == 1

    csv = api_client_no_csrf.get(f"/api/v1/reports/students/export/?selection={token}")
    assert csv.status_code == 200
    body = b"".join(csv.streaming_content).decode()
    assert student_profile.student_id in body
    assert other_student_profile.student_id not in body


@pytest.mark.django_db
def test_a_selection_never_reaches_rows_the_caller_cannot_see(
    api_client_no_csrf, manager_user, student_profile, other_branch_student
):
    """A Jaipur manager who ticks (or forges) a Pune id exports nothing for it."""
    api_client_no_csrf.force_login(manager_user)
    token = _select(api_client_no_csrf, [student_profile.pk, other_branch_student.pk])
    assert _count(api_client_no_csrf, "students", token) == 1


@pytest.mark.django_db
def test_a_selection_belongs_to_the_person_who_made_it(
    api_client_no_csrf, admin_user, manager_user, student_profile
):
    api_client_no_csrf.force_login(admin_user)
    token = _select(api_client_no_csrf, [student_profile.pk])

    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(f"/api/v1/reports/students/count/?selection={token}")
    assert response.status_code == 400
    assert "expired" in str(response.json())


@pytest.mark.django_db
def test_an_unknown_selection_is_refused_rather_than_ignored(api_client_no_csrf, admin_user):
    """Ignoring it would export everything — the opposite of what was asked."""
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get("/api/v1/reports/students/export/?selection=nope")
    assert response.status_code == 400


@pytest.mark.django_db
def test_a_report_that_cannot_narrow_to_rows_refuses_a_selection(
    api_client_no_csrf, admin_user, student_profile
):
    api_client_no_csrf.force_login(admin_user)
    token = _select(api_client_no_csrf, [student_profile.pk])
    response = api_client_no_csrf.get(f"/api/v1/reports/fee_payments/count/?selection={token}")
    assert response.status_code == 400
    assert "selected rows" in str(response.json())


@pytest.mark.django_db
def test_selecting_needs_the_export_right(api_client_no_csrf, trainer_profile, student_profile):
    """A trainer reads reports about their batches but exports nothing; a
    student reads no reports at all."""
    for user in (trainer_profile.user, student_profile.user):
        api_client_no_csrf.force_login(user)
        response = api_client_no_csrf.post(
            SELECTIONS_URL, {"ids": [str(student_profile.pk)]}, format="json"
        )
        assert response.status_code == 403, user.role


@pytest.mark.django_db
def test_a_selection_is_bounded(api_client_no_csrf, admin_user):
    import uuid

    api_client_no_csrf.force_login(admin_user)
    too_many = [str(uuid.uuid4()) for _ in range(MAX_SELECTED + 1)]
    response = api_client_no_csrf.post(SELECTIONS_URL, {"ids": too_many}, format="json")
    assert response.status_code == 400
    empty = api_client_no_csrf.post(SELECTIONS_URL, {"ids": []}, format="json")
    assert empty.status_code == 400


@pytest.mark.django_db
def test_a_queued_export_keeps_the_ticked_rows_after_the_token_is_gone(
    api_client_no_csrf, admin_user, enrollment, other_enrollment
):
    from django.core.cache import cache

    from apps.reporting.models import ExportJob, ExportStatus

    api_client_no_csrf.force_login(admin_user)
    token = _select(api_client_no_csrf, [enrollment.pk])
    response = api_client_no_csrf.post(
        "/api/v1/reports/exports/",
        {"report_key": "enrollments", "format": "xlsx", "selection": token},
        format="json",
    )
    assert response.status_code == 202, response.content
    job = ExportJob.objects.get(pk=response.json()["id"])
    assert job.filters["ids"] == [str(enrollment.pk)]
    assert job.status == ExportStatus.COMPLETED, job.error
    assert job.row_count == 1

    # The worker reads the ids from the job, not the token.
    cache.clear()
    job.status = ExportStatus.QUEUED
    job.save(update_fields=["status"])
    from apps.reporting.tasks import run_export

    run_export(str(job.pk))
    job.refresh_from_db()
    assert job.status == ExportStatus.COMPLETED, job.error
    assert job.row_count == 1


@pytest.mark.django_db
def test_the_accounts_export_is_the_accounts_list(
    api_client_no_csrf, admin_user, manager_user, counsellor_user, other_branch_manager
):
    """Same gate (`user.view_any`), same centre scope and filters as the list."""
    api_client_no_csrf.force_login(admin_user)
    every = _count_query(api_client_no_csrf, "accounts", "")
    assert every >= 3
    assert _count_query(api_client_no_csrf, "accounts", "role=counsellor") == 1
    assert _count_query(api_client_no_csrf, "accounts", "search=Mira") == 1
    # Whatever the list shows, and nothing it does not — for a centre-bound
    # manager too.
    for user in (admin_user, manager_user):
        api_client_no_csrf.force_login(user)
        listed = api_client_no_csrf.get("/api/v1/users/?page_size=100").json()["results"]
        exported = api_client_no_csrf.get("/api/v1/reports/accounts/").json()["rows"]
        assert {row["email"] for row in exported} == {row["email"] for row in listed}
    assert other_branch_manager.email not in {row["email"] for row in exported}

    api_client_no_csrf.force_login(admin_user)
    token = _select(api_client_no_csrf, [manager_user.pk, counsellor_user.pk])
    assert _count(api_client_no_csrf, "accounts", token) == 2


@pytest.mark.django_db
def test_the_accounts_export_is_empty_without_the_accounts_right(
    api_client_no_csrf, trainer_profile, admin_user
):
    api_client_no_csrf.force_login(trainer_profile.user)
    assert api_client_no_csrf.get("/api/v1/reports/accounts/").json()["rows"] == []


def _count_query(client, key: str, query: str) -> int:
    response = client.get(f"/api/v1/reports/{key}/count/?{query}")
    assert response.status_code == 200, response.content
    return response.json()["rows"]


@pytest.mark.django_db
def test_the_students_export_narrows_to_who_a_student_referred(
    api_client_no_csrf, admin_user, student_profile, other_student_profile
):
    """The "Has referred N students" link opens the list filtered by
    `referred_by`; its export is those students, not everyone."""
    other_student_profile.referred_by = student_profile
    other_student_profile.save(update_fields=["referred_by"])
    api_client_no_csrf.force_login(admin_user)
    assert _count_query(api_client_no_csrf, "students", f"referred_by={student_profile.pk}") == 1
