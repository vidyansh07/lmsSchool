"""Warnings: said before things go wrong, only about what the caller can see.

- a fee past its expected date, an enrolment with no fee, a batch with no
  trainer, a finished class with no report, a student registered a week ago
  and not on a batch, a bounded account with no centre — each surfaces with
  a count, a link and the first few names;
- a student gets an empty list; a trainer is warned about their own classes
  and nobody else's; a manager from another centre sees none of this one's;
- the strip is cached for a minute per person.
"""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.warnings import services

URL = "/api/v1/warnings/"


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def trouble(admin_user, counsellor_user, enrollment, published_course, trainer_profile, branch):
    """One of everything that can go wrong at the main centre."""
    from apps.accounts.models import User, UserRole
    from apps.batches.services import create_batch
    from apps.fees import services as fees
    from apps.sessions.models import ClassSession, SessionStatus
    from apps.students.services import create_student

    today = timezone.localdate()
    plan = fees.set_fee_plan(enrollment=enrollment, actor=counsellor_user, agreed_amount="10000")
    fees.record_payment(plan=plan, actor=counsellor_user, amount="1000")
    fees.set_next_due(plan=plan, actor=counsellor_user, amount="3000", on=today - timedelta(days=2))

    unstaffed = create_batch(
        actor=admin_user,
        name="Nobody teaching",
        course=published_course,
        trainer=None,
        start_date=today + timedelta(days=2),
        end_date=today + timedelta(days=60),
        capacity=10,
    )
    session = ClassSession.objects.create(
        batch=enrollment.batch,
        session_date=today - timedelta(days=1),
        start_time=time(9, 0),
        end_time=time(11, 0),
        status=SessionStatus.COMPLETED,
        trainer=trainer_profile,
    )
    waiting = create_student(
        email="waiting@example.test",
        first_name="Waiting",
        actor=counsellor_user,
        password="Str0ng-Passphrase!42",
        send_invitation=False,
    )
    waiting.created_at = timezone.now() - timedelta(days=8)
    waiting.save(update_fields=["created_at"])
    lost = User.objects.create_user(
        email="lost@example.test",
        password="Str0ng-Passphrase!42",
        first_name="Lost",
        role=UserRole.MANAGER,
        branch=None,
    )
    return {
        "plan": plan,
        "unstaffed": unstaffed,
        "session": session,
        "waiting": waiting,
        "lost": lost,
    }


def _by_kind(rows):
    return {row["kind"]: row for row in rows}


@pytest.mark.django_db
def test_an_administrator_is_warned_about_everything(api_client_no_csrf, admin_user, trouble):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(URL)
    assert response.status_code == 200, response.data
    found = _by_kind(response.json())
    assert found["fees_overdue"]["count"] == 1
    assert "₹9,000 owed" in found["fees_overdue"]["items"][0]["label"]
    assert found["fees_overdue"]["items"][0]["href"].startswith("/admissions/")
    assert found["batch_no_trainer"]["count"] == 1
    assert (
        found["batch_no_trainer"]["items"][0]["href"] == f"/admin/batches/{trouble['unstaffed'].pk}"
    )
    assert found["batch_seats"]["count"] == 1
    assert found["dsr_missing"]["count"] == 1
    assert found["dsr_missing"]["items"][0]["href"] == f"/teaching/sessions/{trouble['session'].pk}"
    assert found["not_enrolled"]["count"] == 1
    assert found["account_no_centre"]["count"] == 1
    assert found["account_no_centre"]["items"][0]["href"] == f"/admin/users/{trouble['lost'].pk}"
    # Most urgent first.
    severities = [row["severity"] for row in response.json()]
    assert severities == sorted(severities, key=lambda s: {"error": 0, "warning": 1, "info": 2}[s])


@pytest.mark.django_db
def test_a_student_is_refused_rather_than_handed_an_empty_list(
    api_client_no_csrf, student_profile, trouble
):
    api_client_no_csrf.force_login(student_profile.user)
    assert api_client_no_csrf.get(URL).status_code == 403
    assert services.warnings_for(student_profile.user) == []


@pytest.mark.django_db
def test_a_trainer_sees_only_their_own_classes(api_client_no_csrf, trainer_profile, trouble):
    api_client_no_csrf.force_login(trainer_profile.user)
    found = _by_kind(api_client_no_csrf.get(URL).json())
    assert "dsr_missing" in found
    assert "fees_overdue" not in found
    assert "account_no_centre" not in found
    assert "batch_no_trainer" not in found


@pytest.mark.django_db
def test_a_manager_from_another_centre_sees_none_of_it(
    api_client_no_csrf, other_branch_manager, trouble
):
    api_client_no_csrf.force_login(other_branch_manager)
    found = _by_kind(api_client_no_csrf.get(URL).json())
    assert "fees_overdue" not in found
    assert "batch_no_trainer" not in found
    assert "dsr_missing" not in found
    assert "not_enrolled" not in found


@pytest.mark.django_db
def test_the_strip_is_cached_for_a_minute(admin_user, trouble):
    first = services.cached_warnings_for(admin_user)
    assert any(w["kind"] == "batch_no_trainer" for w in first)
    from apps.batches.services import assign_trainer

    assign_trainer(batch=trouble["unstaffed"], trainer=None, actor=admin_user)
    trouble["unstaffed"].delete()
    again = services.cached_warnings_for(admin_user)
    assert again == first
    cache.clear()
    fresh = services.cached_warnings_for(admin_user)
    assert not any(w["kind"] == "batch_no_trainer" for w in fresh)


@pytest.mark.django_db
def test_the_weekly_digest_notifies_staff_with_open_warnings(admin_user, student_profile, trouble):
    from apps.notifications.models import Notification, NotificationKind
    from apps.warnings.tasks import weekly_digest

    sent = weekly_digest()
    assert sent >= 1
    note = Notification.objects.get(recipient=admin_user, kind=NotificationKind.WARNING_DIGEST)
    assert "need attention" in note.title
    assert "no trainer" in note.body
    assert not Notification.objects.filter(recipient=student_profile.user).exists()
