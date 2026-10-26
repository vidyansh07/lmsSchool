"""Holding a result back from the student until somebody releases it.

The case this exists for is a mock interview. A trainer scores one and writes
a paragraph about how the student came across — and until now, because the
interview types in the seeded catalogue are `visible_to_student=True` and
`create_activity` resolves an instance's flag from its type, that paragraph
was published the instant it was saved. The first draft, typed while the
student was still in the room, was the thing the student read.

The owner's decision (26 October 2026) is that a result is written privately
and published by a deliberate act. What is pinned here:

- a type marked `release_required` creates its activities **hidden**, whatever
  the caller passes, including a caller passing `student_visible=True`;
- the student sees that the interview happened and nothing of the result;
- only the person who did the work, or somebody with `activity.review`, may
  release it — and either way it is one audited act;
- the audit row records the decision and the row, never the feedback text;
- the flag is meaningless without `visible_to_student`, so setting it alone is
  refused rather than silently ignored.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.work import services
from apps.work.models import Activity, ActivityType

pytestmark = pytest.mark.django_db


def _interview_type(**overrides) -> ActivityType:
    defaults = {
        "slug": f"mock-{ActivityType.objects.count()}",
        "name": "Mock Interview",
        "category": "interview",
        "allowed_creator_roles": ["admin", "superadmin", "manager", "counsellor"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
        "release_required": True,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _student_sees(student_profile) -> list[Activity]:
    from apps.work import access

    return list(access.student_visible_activities(student_profile))


# ---------------------------------------------------------------------------
# It starts hidden, and stays hidden
# ---------------------------------------------------------------------------


def test_an_interview_starts_hidden_from_the_student(admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )

    assert activity.student_visible is False
    assert _student_sees(student_profile) == []


def test_a_caller_cannot_publish_it_at_creation(admin_user, student_profile):
    # The type is visible to students, so `student_visible=True` would
    # ordinarily be accepted. `release_required` is exactly the thing that
    # must not be overridable by the caller that creates the row.
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=_interview_type(),
        student_visible=True,
    )

    assert activity.student_visible is False
    assert _student_sees(student_profile) == []


def test_scoring_it_does_not_publish_it(admin_user, student_profile, enrollment, trainer_profile):
    trainer_user = trainer_profile.user
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=_interview_type(),
        enrollment=enrollment,
        assigned_to=trainer_user,
        planned_at=timezone.now() + timedelta(hours=1),
    )
    for actor, status in (
        (admin_user, "planned"),
        (admin_user, "assigned"),
        (trainer_user, "in_progress"),
    ):
        services.transition_activity(actor=actor, activity=activity, to_status=status)
    services.complete_activity(
        actor=trainer_user,
        activity=activity,
        summary="Clear on Linux; slow on behavioural questions.",
    )
    # A real mock interview's score arrives through the type's form, which
    # this test deliberately does not stand up: what is being pinned is that
    # a *scored, completed* interview is still not visible, and the route the
    # number took to get there is not what decides that.
    Activity.objects.filter(pk=activity.pk).update(
        score=Decimal("7"), max_score=Decimal("10"), result="pass"
    )

    activity.refresh_from_db()
    assert activity.score == Decimal("7")
    # The score exists and the student still cannot reach it.
    assert activity.student_visible is False
    assert _student_sees(student_profile) == []


# ---------------------------------------------------------------------------
# Releasing it
# ---------------------------------------------------------------------------


def test_releasing_shows_the_student_the_result(admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )

    services.release_activity(actor=admin_user, activity=activity)

    activity.refresh_from_db()
    assert activity.student_visible is True
    assert [row.pk for row in _student_sees(student_profile)] == [activity.pk]


def test_the_person_who_did_the_work_may_release_it(
    admin_user, student_profile, enrollment, trainer_profile
):
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=_interview_type(),
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )

    # A trainer holds no activity capability at all — their reach here is the
    # assignment, which is the whole point of letting the performer release.
    services.release_activity(actor=trainer_profile.user, activity=activity)

    activity.refresh_from_db()
    assert activity.student_visible is True


def test_somebody_unrelated_cannot_release_it(admin_user, trainer, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )

    # This trainer neither performed it nor was assigned it, and holds no
    # review capability.
    with pytest.raises(AuthorityError):
        services.release_activity(actor=trainer, activity=activity)

    activity.refresh_from_db()
    assert activity.student_visible is False


def test_a_result_can_be_taken_back(admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )
    services.release_activity(actor=admin_user, activity=activity)

    services.release_activity(actor=admin_user, activity=activity, released=False)

    activity.refresh_from_db()
    assert activity.student_visible is False
    assert _student_sees(student_profile) == []


def test_releasing_twice_changes_nothing_and_records_nothing(admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )
    services.release_activity(actor=admin_user, activity=activity)
    before = AuditLog.objects.filter(action=AuditAction.ACTIVITY_RELEASED).count()

    services.release_activity(actor=admin_user, activity=activity)

    assert AuditLog.objects.filter(action=AuditAction.ACTIVITY_RELEASED).count() == before


# ---------------------------------------------------------------------------
# What the flag may and may not be set on
# ---------------------------------------------------------------------------


def test_releasing_an_ordinary_activity_is_refused(admin_user, student_profile):
    ordinary = _interview_type(slug="ordinary", release_required=False)
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=ordinary
    )

    # Nothing is held back here, so there is nothing to release. Refused
    # rather than quietly succeeding: the caller has misunderstood something.
    with pytest.raises(ApplicationError):
        services.release_activity(actor=admin_user, activity=activity)


def test_holding_back_a_type_students_cannot_see_is_refused(admin_user):
    with pytest.raises(ApplicationError) as excinfo:
        services.create_activity_type(
            actor=admin_user,
            slug="pointless-hold",
            name="Pointless",
            category="interview",
            allowed_creator_roles=["admin"],
            allowed_assignee_roles=["trainer"],
            visible_to_student=False,
            release_required=True,
        )

    assert "release_required" in excinfo.value.detail


def test_turning_visibility_off_under_a_held_type_is_refused(admin_user):
    activity_type = services.create_activity_type(
        actor=admin_user,
        slug="held",
        name="Held",
        category="interview",
        allowed_creator_roles=["admin"],
        allowed_assignee_roles=["trainer"],
        visible_to_student=True,
        release_required=True,
    )

    with pytest.raises(ApplicationError):
        services.update_activity_type(
            actor=admin_user, activity_type=activity_type, visible_to_student=False
        )


# ---------------------------------------------------------------------------
# The audit trail
# ---------------------------------------------------------------------------


def test_the_audit_records_the_decision_and_not_the_feedback(admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=_interview_type(),
        summary="Hesitant under pressure; the family situation came up.",
    )

    services.release_activity(actor=admin_user, activity=activity)

    entry = AuditLog.objects.get(action=AuditAction.ACTIVITY_RELEASED)
    assert entry.context["released"] is True
    assert entry.context["student_id"] == str(student_profile.pk)
    # A mock interview's feedback is a paragraph about a person, and the audit
    # trail is read far more widely than the activity is.
    assert "family" not in str(entry.context)


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_the_endpoint_releases_it(api_client_no_csrf, admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )

    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(
        f"/api/v1/activities/{activity.pk}/release/", {}, format="json"
    )

    assert response.status_code == 200, response.json()
    activity.refresh_from_db()
    assert activity.student_visible is True


def test_a_student_cannot_release_their_own_result(api_client_no_csrf, admin_user, student_profile):
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=_interview_type()
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        f"/api/v1/activities/{activity.pk}/release/", {}, format="json"
    )

    # The staff activity queryset does not contain it for them, so this is the
    # 404 a guessed id gets rather than a 403 confirming it exists.
    assert response.status_code in (403, 404)
    activity.refresh_from_db()
    assert activity.student_visible is False
