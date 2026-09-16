"""The activity engine's services (ERP Phase 9): create, complete, review,
delete, and the seed migration's catalog.

Fixtures come from `tests/conftest.py` — `student_profile`/`trainer_profile`/
`batch`/`enrollment`/`admin_user`/`manager_user`/`counsellor_user` — the same
set every other phase's tests build on; nothing here invents a new factory.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connection

from apps.common.exceptions import ApplicationError, AuthorityError
from apps.forms.models import FormDefinition, FormField, FormVersion, FormVersionStatus
from apps.work import services
from apps.work.models import (
    Activity,
    ActivityResult,
    ActivityStatus,
    ActivityType,
    ActivityTypeStatus,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_type(**overrides):
    defaults = {
        "slug": f"test-type-{ActivityType.objects.count()}",
        "name": "Test Type",
        "category": "mentoring",
        "allowed_creator_roles": ["manager", "trainer"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
        "requires_review": False,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


def _published_form_with_score(slug="score-form", max_score=10):
    definition = FormDefinition.objects.create(slug=slug, name="Score form", entity="activity")
    version = FormVersion.objects.create(
        definition=definition, number=1, status=FormVersionStatus.PUBLISHED
    )
    FormField.objects.create(
        version=version,
        key="score",
        label="Score",
        type="decimal",
        required=True,
        order=0,
        validation={"min": 0, "max": max_score},
        performance_key="score",
    )
    return definition


# ---------------------------------------------------------------------------
# create_activity
# ---------------------------------------------------------------------------


def test_create_activity_refuses_a_creator_role_outside_the_type_allowlist(
    manager_user, student_profile
):
    activity_type = _make_type(allowed_creator_roles=["trainer"])
    with pytest.raises(AuthorityError):
        services.create_activity(
            actor=manager_user, student=student_profile, activity_type=activity_type
        )


def test_create_activity_lets_admin_bypass_the_type_allowlist(admin_user, student_profile):
    """The allowlist narrows the day-to-day roles; it never withholds from
    the rung that maintains the catalog itself."""
    activity_type = _make_type(allowed_creator_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=activity_type
    )
    assert activity.status == ActivityStatus.DRAFT
    assert activity.created_by_id == admin_user.pk


def test_create_activity_refuses_an_assignee_role_outside_the_type_allowlist(
    admin_user, student_profile, counsellor_user
):
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    with pytest.raises(ApplicationError):
        services.create_activity(
            actor=admin_user,
            student=student_profile,
            activity_type=activity_type,
            assigned_to=counsellor_user,
        )


def test_create_activity_refuses_an_assignee_outside_the_acting_scope(
    admin_user, student_profile, trainer_profile_two
):
    """`trainer_profile_two` teaches no batch this student is on."""
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    with pytest.raises(ApplicationError):
        services.create_activity(
            actor=admin_user,
            student=student_profile,
            activity_type=activity_type,
            assigned_to=trainer_profile_two.user,
        )


def test_create_activity_accepts_an_assignee_within_scope(
    admin_user, student_profile, enrollment, trainer_profile
):
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    assert activity.assigned_to_id == trainer_profile.user.pk
    assert activity.batch_id == enrollment.batch_id


def test_create_activity_may_override_visibility_to_hidden_but_not_to_visible(
    admin_user, student_profile
):
    hidden_type = _make_type(visible_to_student=False)
    with pytest.raises(ApplicationError):
        services.create_activity(
            actor=admin_user,
            student=student_profile,
            activity_type=hidden_type,
            student_visible=True,
        )

    visible_type = _make_type(visible_to_student=True)
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=visible_type,
        student_visible=False,
    )
    assert activity.student_visible is False


def test_create_activity_pins_the_published_form_version(admin_user, student_profile):
    definition = _published_form_with_score()
    activity_type = _make_type(form=definition)
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=activity_type
    )
    assert activity.form_version.definition_id == definition.pk
    assert activity.form_version.status == FormVersionStatus.PUBLISHED


def test_create_activity_refuses_a_type_whose_form_has_no_published_version(
    admin_user, student_profile
):
    definition = FormDefinition.objects.create(slug="draft-only", name="Draft", entity="activity")
    FormVersion.objects.create(definition=definition, number=1, status=FormVersionStatus.DRAFT)
    activity_type = _make_type(form=definition)
    with pytest.raises(ApplicationError):
        services.create_activity(
            actor=admin_user, student=student_profile, activity_type=activity_type
        )


def test_create_activity_refuses_a_disabled_type(admin_user, student_profile):
    activity_type = _make_type(status=ActivityTypeStatus.DISABLED)
    with pytest.raises(ApplicationError):
        services.create_activity(
            actor=admin_user, student=student_profile, activity_type=activity_type
        )


def test_create_activity_client_key_retry_returns_the_existing_row(admin_user, student_profile):
    activity_type = _make_type()
    first = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=activity_type, client_key="retry-1"
    )
    second = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=activity_type, client_key="retry-1"
    )
    assert first.pk == second.pk
    assert Activity.objects.filter(client_key="retry-1").count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_creates_with_the_same_client_key_make_one_row(
    admin_user, student_profile
):
    """The genuine concurrent race `AGENT_PLAYBOOK.md` calls for — mirrors
    `tests/test_otp.py::test_two_simultaneous_sends_only_one_succeeds`'s
    two-thread-and-a-barrier shape."""
    activity_type = _make_type()
    results: list = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        try:
            barrier.wait(timeout=5)
            activity = services.create_activity(
                actor=admin_user,
                student=student_profile,
                activity_type=activity_type,
                client_key="race-key",
            )
            results.append(activity.pk)
        except Exception as exc:  # pragma: no cover - surfaced via `errors`
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert len(results) == 2
    assert len(set(results)) == 1
    assert Activity.objects.filter(client_key="race-key").count() == 1


# ---------------------------------------------------------------------------
# complete_activity
# ---------------------------------------------------------------------------


def _assigned_activity(*, admin_user, student_profile, trainer_profile, enrollment, **type_kwargs):
    """An ASSIGNED activity, with `enrollment` denormalising the batch so
    the trainer's `assigned`-scope check has something to match against."""
    activity_type = _make_type(allowed_assignee_roles=["trainer"], **type_kwargs)
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=None,
    )
    activity.status = ActivityStatus.ASSIGNED
    activity.save(update_fields=["status"])
    return activity


def test_complete_activity_validates_the_form_and_derives_score_and_result(
    admin_user, student_profile, trainer_profile, enrollment
):
    definition = _published_form_with_score(slug="pass-fail-form")
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
        form=definition,
    )
    completed = services.complete_activity(
        actor=trainer_profile.user, activity=activity, form_values={"score": "8"}
    )
    assert completed.status == ActivityStatus.COMPLETED
    assert completed.score == 8
    assert completed.max_score == 10
    assert completed.result == ActivityResult.PASS
    assert completed.form_response is not None


def test_complete_activity_derives_a_failing_result_below_the_threshold(
    admin_user, student_profile, trainer_profile, enrollment
):
    definition = _published_form_with_score(slug="low-score-form")
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
        form=definition,
    )
    completed = services.complete_activity(
        actor=trainer_profile.user, activity=activity, form_values={"score": "3"}
    )
    assert completed.result == ActivityResult.FAIL


def test_complete_activity_requiring_review_moves_to_under_review(
    admin_user, student_profile, trainer_profile, enrollment
):
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
        requires_review=True,
    )
    completed = services.complete_activity(
        actor=trainer_profile.user, activity=activity, form_values={}
    )
    assert completed.status == ActivityStatus.UNDER_REVIEW


def test_complete_activity_not_requiring_review_moves_straight_to_completed(
    admin_user, student_profile, trainer_profile, enrollment
):
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
        requires_review=False,
    )
    completed = services.complete_activity(
        actor=trainer_profile.user, activity=activity, form_values={}
    )
    assert completed.status == ActivityStatus.COMPLETED


def test_completing_an_already_completed_activity_is_409(
    admin_user, student_profile, trainer_profile, enrollment
):
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
    )
    services.complete_activity(actor=trainer_profile.user, activity=activity, form_values={})
    with pytest.raises(services.TransitionError) as exc:
        services.complete_activity(actor=trainer_profile.user, activity=activity, form_values={})
    assert exc.value.status_code == 409


def test_complete_activity_refuses_someone_outside_authority(
    admin_user, student_profile, trainer_profile, trainer_profile_two, enrollment
):
    """`trainer_profile_two` is neither the assignee nor a holder of
    `activity.complete` covering this batch — a counsellor or manager would
    genuinely hold branch-scoped `activity.complete` and is not the right
    negative case here."""
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
    )
    with pytest.raises(AuthorityError):
        services.complete_activity(
            actor=trainer_profile_two.user, activity=activity, form_values={}
        )


# ---------------------------------------------------------------------------
# review_activity
# ---------------------------------------------------------------------------


def _under_review_activity(*, admin_user, student_profile, trainer_profile, enrollment):
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
        requires_review=True,
    )
    return services.complete_activity(actor=trainer_profile.user, activity=activity, form_values={})


def test_review_refuses_the_performer_reviewing_their_own_work(
    admin_user, student_profile, trainer_profile, enrollment
):
    activity = _under_review_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
    )
    with pytest.raises(AuthorityError):
        services.review_activity(
            actor=trainer_profile.user, activity=activity, decision="approved", note=""
        )


def test_review_approves(admin_user, student_profile, trainer_profile, manager_user, enrollment):
    activity = _under_review_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
    )
    reviewed = services.review_activity(
        actor=manager_user, activity=activity, decision="approved", note=""
    )
    assert reviewed.status == ActivityStatus.APPROVED
    assert reviewed.reviewed_by_id == manager_user.pk


def test_review_requires_action_needs_a_note(
    admin_user, student_profile, trainer_profile, manager_user, enrollment
):
    activity = _under_review_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
    )
    with pytest.raises(ApplicationError):
        services.review_activity(
            actor=manager_user, activity=activity, decision="requires_action", note=""
        )
    reviewed = services.review_activity(
        actor=manager_user,
        activity=activity,
        decision="requires_action",
        note="Redo the summary.",
    )
    assert reviewed.status == ActivityStatus.REQUIRES_ACTION


def test_review_only_legal_from_under_review(
    admin_user, student_profile, trainer_profile, manager_user, enrollment
):
    activity = _assigned_activity(
        admin_user=admin_user,
        student_profile=student_profile,
        trainer_profile=trainer_profile,
        enrollment=enrollment,
    )
    with pytest.raises(services.TransitionError):
        services.review_activity(
            actor=manager_user, activity=activity, decision="approved", note=""
        )


# ---------------------------------------------------------------------------
# delete_activity
# ---------------------------------------------------------------------------


def test_delete_activity_soft_deletes(admin_user, student_profile):
    activity_type = _make_type()
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=activity_type
    )
    services.delete_activity(actor=admin_user, activity=activity, reason="Created by mistake.")
    activity.refresh_from_db()
    assert activity.deleted_at is not None
    assert not Activity.objects.filter(pk=activity.pk).exists()
    assert Activity.all_objects.filter(pk=activity.pk).exists()


def test_delete_activity_refuses_without_authority(admin_user, student_profile, trainer_profile):
    activity_type = _make_type()
    activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=activity_type
    )
    with pytest.raises(AuthorityError):
        services.delete_activity(actor=trainer_profile.user, activity=activity, reason="Nope.")


# ---------------------------------------------------------------------------
# The seed migration's catalog
# ---------------------------------------------------------------------------


def test_the_seed_migration_created_18_system_types():
    assert ActivityType.objects.filter(is_system=True).count() == 18


def test_a_seeded_type_carries_its_catalog_fields():
    mock_interview = ActivityType.objects.get(slug="mock-interview")
    assert mock_interview.category == "interview"
    assert mock_interview.allowed_creator_roles == ["manager", "trainer"]
    assert mock_interview.allowed_assignee_roles == ["trainer"]
    assert mock_interview.visible_to_student is True
    assert mock_interview.default_duration_minutes == 30
    assert mock_interview.requires_review is False
    assert str(mock_interview.performance_weight) == "1.00"
    assert mock_interview.risk_effect == "score_below_threshold"
    assert mock_interview.form.slug == "mock-interview"
    assert mock_interview.next_action["create_type"] == "communication-practice"


def test_a_seeded_type_with_no_form_stores_none():
    performance_review = ActivityType.objects.get(slug="performance-review")
    assert performance_review.form_id is None


def test_seeded_types_requiring_review():
    requiring_review = set(
        ActivityType.objects.filter(requires_review=True).values_list("slug", flat=True)
    )
    assert requiring_review == {"project-review", "warning"}
