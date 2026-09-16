"""Capability and scope gating on the activity engine's endpoints.

Every case is checked against a real record (never a guessed id): a
cross-branch or cross-batch id 404s through the `visible_*` queryset —
never a 403 that would confirm the record exists — and a student sees only
`visible_to_student` activities and only `visible_to_student` form fields.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.forms.models import FormDefinition, FormField, FormVersion, FormVersionStatus
from apps.work import services
from apps.work.models import ActivityStatus, ActivityType

pytestmark = pytest.mark.django_db

ACTIVITIES = "/api/v1/activities/"
ACTIVITY_TYPES = "/api/v1/activity-types/"


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _make_type(**overrides):
    defaults = {
        "slug": f"vis-{ActivityType.objects.count()}",
        "name": "Visibility Test Type",
        "category": "mentoring",
        "allowed_creator_roles": ["admin", "superadmin", "manager", "trainer", "counsellor"],
        "allowed_assignee_roles": ["trainer"],
        "visible_to_student": True,
    }
    defaults.update(overrides)
    return ActivityType.objects.create(**defaults)


# ---------------------------------------------------------------------------
# activity-types: any staff reads, activity_type.manage writes
# ---------------------------------------------------------------------------


def test_a_student_cannot_read_the_activity_catalog(student_profile):
    response = _client(student_profile.user).get(ACTIVITY_TYPES)
    assert response.status_code == 403


def test_any_staff_role_reads_the_activity_catalog(trainer, counsellor_user, manager_user):
    for user in (trainer, counsellor_user, manager_user):
        response = _client(user).get(ACTIVITY_TYPES)
        assert response.status_code == 200
        assert "results" in response.json()


def test_only_activity_type_manage_may_write_the_catalog(manager_user, admin_user):
    body = {
        "slug": "custom-type",
        "name": "Custom",
        "description": "",
        "category": "other",
        "allowed_creator_roles": ["manager"],
        "allowed_assignee_roles": [],
        "visible_to_student": False,
    }
    denied = _client(manager_user).post(ACTIVITY_TYPES, body, format="json")
    assert denied.status_code == 403

    allowed = _client(admin_user).post(ACTIVITY_TYPES, body, format="json")
    assert allowed.status_code == 201


# ---------------------------------------------------------------------------
# activities: all/branch/assigned(-by-teaching) tiers
# ---------------------------------------------------------------------------


def test_manager_sees_activities_in_their_own_branch_only(
    admin_user, manager_user, student_profile, other_branch_manager, other_branch_student
):
    activity_type = _make_type()
    services.create_activity(actor=admin_user, student=student_profile, activity_type=activity_type)
    services.create_activity(
        actor=other_branch_manager, student=other_branch_student, activity_type=activity_type
    )

    seen = _client(manager_user).get(ACTIVITIES).json()["results"]
    students = {row["student"]["id"] for row in seen}
    assert str(student_profile.pk) in students
    assert str(other_branch_student.pk) not in students


def test_superadmin_sees_every_branch(
    unbounded_superadmin, admin_user, student_profile, other_branch_manager, other_branch_student
):
    activity_type = _make_type()
    services.create_activity(actor=admin_user, student=student_profile, activity_type=activity_type)
    services.create_activity(
        actor=other_branch_manager, student=other_branch_student, activity_type=activity_type
    )

    seen = _client(unbounded_superadmin).get(ACTIVITIES).json()["results"]
    students = {row["student"]["id"] for row in seen}
    assert str(student_profile.pk) in students
    assert str(other_branch_student.pk) in students


def test_a_trainer_sees_only_activities_on_batches_they_teach(
    admin_user, trainer_profile, trainer_profile_two, student_profile, enrollment
):
    """A trainer holds no `activity.*` capability at all (`apps.work.access`'s
    module docstring) — their reach is resolved per batch, capability-free."""
    activity_type = _make_type()
    mine = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )

    seen = _client(trainer_profile.user).get(ACTIVITIES).json()["results"]
    ids = {row["id"] for row in seen}
    assert str(mine.pk) in ids

    seen_by_other = _client(trainer_profile_two.user).get(ACTIVITIES).json()["results"]
    assert str(mine.pk) not in {row["id"] for row in seen_by_other}


def test_a_trainer_still_sees_an_activity_they_are_assigned_after_the_batch_context_is_gone(
    admin_user, trainer_profile, trainer_profile_two, student_profile, enrollment
):
    """Assignee/creator visibility does not depend on *still* teaching the
    batch — the same reasoning `apps.dsr.access.visible_dsrs` gives its own
    trainer ("the batches this trainer teaches now, not only the reports
    they wrote")."""
    activity_type = _make_type()
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    # The batch is reassigned to a different trainer after the fact — the
    # activity's own `assigned_to` does not move with it.
    enrollment.batch.trainer = trainer_profile_two
    enrollment.batch.save(update_fields=["trainer"])

    seen = _client(trainer_profile.user).get(ACTIVITIES).json()["results"]
    assert str(activity.pk) in {row["id"] for row in seen}


def test_review_refuses_the_performer_even_though_they_hold_activity_review(
    admin_user, counsellor_user, student_profile
):
    """D-130 gives a counsellor the same `activity.review`/`activity.delete`
    a manager holds (`tests/test_counsellor_rbac.py`) — but holding the
    capability is not sufficient when the caller is also the one whose work
    it is; self-review stays refused regardless of rung."""
    activity_type = _make_type(requires_review=True, allowed_assignee_roles=["counsellor"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        assigned_to=counsellor_user,
    )
    activity.status = ActivityStatus.UNDER_REVIEW
    activity.save(update_fields=["status"])

    response = _client(counsellor_user).post(
        f"{ACTIVITIES}{activity.pk}/review/", {"decision": "approved", "note": ""}, format="json"
    )
    assert response.status_code == 403


def test_a_trainer_holds_no_activity_delete(
    admin_user, trainer_profile, student_profile, enrollment
):
    """Unlike a counsellor (D-130), a trainer holds neither `activity.review`
    nor `activity.delete` — the catalog keeps both at the manager rung and
    above. `delete` has no self-check at all (unlike review), so it isolates
    "no capability" cleanly rather than overlapping with self-review."""
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    delete_response = _client(trainer_profile.user).delete(
        f"{ACTIVITIES}{activity.pk}/", {"reason": "test"}, format="json"
    )
    assert delete_response.status_code == 403


def test_cross_branch_activity_id_404s_not_403(
    admin_user, manager_user, other_branch_manager, other_branch_student
):
    """A guessed id from another centre resolves to nothing — never a 403
    that would confirm the record exists (rule 2)."""
    activity_type = _make_type()
    theirs = services.create_activity(
        actor=other_branch_manager, student=other_branch_student, activity_type=activity_type
    )
    response = _client(manager_user).get(f"{ACTIVITIES}{theirs.pk}/")
    assert response.status_code == 404


def test_cross_batch_trainer_gets_404_not_403(
    admin_user, trainer_profile_two, student_profile, trainer_profile, enrollment
):
    """A trainer who does not teach the batch gets the same 404 a completely
    unrelated caller would — not a 403 that leaks the row's existence."""
    activity_type = _make_type()
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    response = _client(trainer_profile_two.user).get(f"{ACTIVITIES}{activity.pk}/")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Student visibility: only visible_to_student activities and fields
# ---------------------------------------------------------------------------


def _published_version_with_student_and_staff_fields():
    definition = FormDefinition.objects.create(
        slug="mixed-visibility", name="Mixed", entity="activity"
    )
    version = FormVersion.objects.create(
        definition=definition, number=1, status=FormVersionStatus.PUBLISHED
    )
    FormField.objects.create(
        version=version,
        key="public_note",
        label="Public note",
        type="text",
        order=0,
        visible_to_student=True,
    )
    FormField.objects.create(
        version=version,
        key="private_note",
        label="Private note",
        type="text",
        order=1,
        visible_to_student=False,
    )
    return definition


def test_a_student_only_sees_visible_to_student_activities(admin_user, student_profile):
    visible_type = _make_type(visible_to_student=True)
    hidden_type = _make_type(visible_to_student=False)
    visible_activity = services.create_activity(
        actor=admin_user, student=student_profile, activity_type=visible_type
    )
    services.create_activity(actor=admin_user, student=student_profile, activity_type=hidden_type)

    response = _client(student_profile.user).get(
        f"/api/v1/students/{student_profile.pk}/activities/"
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert ids == {str(visible_activity.pk)}


def test_a_student_sees_only_visible_to_student_form_fields(
    admin_user, student_profile, trainer_profile, enrollment
):
    definition = _published_version_with_student_and_staff_fields()
    activity_type = _make_type(form=definition, allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    activity.status = ActivityStatus.ASSIGNED
    activity.save(update_fields=["status"])
    services.complete_activity(
        actor=trainer_profile.user,
        activity=activity,
        form_values={"public_note": "Nice work", "private_note": "Watch attendance"},
    )

    staff_view = _client(trainer_profile.user).get(f"{ACTIVITIES}{activity.pk}/").json()
    assert set(staff_view["form_values"]) == {"public_note", "private_note"}
    assert {f["key"] for f in staff_view["form"]["fields"]} == {"public_note", "private_note"}

    student_view = _client(student_profile.user).get(
        f"/api/v1/students/{student_profile.pk}/activities/"
    )
    assert student_view.status_code == 200
    # The list row never carries form values regardless of caller — only
    # detail does, and the student reaches detail through the same nested
    # route with the activity's own id.
    detail = _client(student_profile.user).get(f"{ACTIVITIES}{activity.pk}/").json()
    assert set(detail["form_values"]) == {"public_note"}
    assert {f["key"] for f in detail["form"]["fields"]} == {"public_note"}


def test_a_student_never_sees_history_notes_actors_or_changes(
    admin_user, student_profile, trainer_profile, enrollment
):
    """`note`, `changes` and `actor` on a history entry are free-text staff
    commentary and provenance with no `visible_to_student` flag of their own
    — unlike `form`/`form_values`, a student caller gets none of the three,
    only the bare status transition."""
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
        planned_at=timezone.now() + timedelta(days=1),
    )
    services.transition_activity(
        actor=admin_user, activity=activity, to_status=ActivityStatus.PLANNED
    )
    activity.refresh_from_db()
    services.transition_activity(
        actor=admin_user,
        activity=activity,
        to_status=ActivityStatus.CANCELLED,
        note="Student withdrew from the batch.",
    )
    activity.refresh_from_db()

    staff_view = _client(trainer_profile.user).get(f"{ACTIVITIES}{activity.pk}/").json()
    cancelled_entry = next(h for h in staff_view["history"] if h["to_status"] == "cancelled")
    assert cancelled_entry["note"] == "Student withdrew from the batch."
    assert cancelled_entry["actor"]["id"] == str(admin_user.pk)
    assert cancelled_entry["changes"]

    student_view = _client(student_profile.user).get(
        f"/api/v1/students/{student_profile.pk}/activities/"
    )
    assert student_view.status_code == 200
    detail = _client(student_profile.user).get(f"{ACTIVITIES}{activity.pk}/").json()
    cancelled_entry = next(h for h in detail["history"] if h["to_status"] == "cancelled")
    assert cancelled_entry["note"] == ""
    assert cancelled_entry["actor"] is None
    assert cancelled_entry["changes"] == {}
    # The transition itself is still visible — only the commentary is hidden.
    assert cancelled_entry["from_status"] == "planned"


def _published_version_with_a_hidden_score_field():
    definition = FormDefinition.objects.create(
        slug="hidden-score", name="Hidden Score", entity="activity"
    )
    version = FormVersion.objects.create(
        definition=definition, number=1, status=FormVersionStatus.PUBLISHED
    )
    FormField.objects.create(
        version=version,
        key="score",
        label="Score",
        type="number",
        order=0,
        visible_to_student=False,
        performance_key="score",
        validation={"max": 10},
    )
    return definition


def test_a_student_cannot_see_a_score_derived_from_a_hidden_field(
    admin_user, student_profile, trainer_profile, enrollment
):
    """`services._extract_score` derives `score`/`max_score`/`result` from
    one form field — the field flagged `performance_key` — regardless of
    that field's own `visible_to_student` flag. The top-level fields on the
    detail response must still honour it, the same as `form`/`form_values`
    do."""
    definition = _published_version_with_a_hidden_score_field()
    activity_type = _make_type(
        form=definition, allowed_assignee_roles=["trainer"], visible_to_student=True
    )
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    activity.status = ActivityStatus.ASSIGNED
    activity.save(update_fields=["status"])
    services.complete_activity(
        actor=trainer_profile.user, activity=activity, form_values={"score": 9}
    )

    staff_view = _client(trainer_profile.user).get(f"{ACTIVITIES}{activity.pk}/").json()
    assert staff_view["score"] == "9.00"
    assert staff_view["max_score"] == "10.00"
    assert staff_view["result"] == "pass"

    detail = _client(student_profile.user).get(f"{ACTIVITIES}{activity.pk}/").json()
    assert detail["score"] is None
    assert detail["max_score"] is None
    assert detail["result"] == "n/a"


def test_a_student_cannot_reach_another_students_activity(
    admin_user, student_profile, other_student_profile
):
    activity_type = _make_type(visible_to_student=True)
    theirs = services.create_activity(
        actor=admin_user, student=other_student_profile, activity_type=activity_type
    )
    response = _client(student_profile.user).get(f"{ACTIVITIES}{theirs.pk}/")
    assert response.status_code == 404


def test_a_student_cannot_reach_another_students_activity_list(
    admin_user, student_profile, other_student_profile
):
    response = _client(student_profile.user).get(
        f"/api/v1/students/{other_student_profile.pk}/activities/"
    )
    # `visible_students` scopes both to the same branch, so the id resolves —
    # `can_view_student` is what refuses a classmate, and it is a 403 by
    # design (`apps.students.access.reachable_students`'s own docstring),
    # not a 404: the record set (the branch) is real, the audience is not.
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Student 360 tab (`GET /students/{id}/activities/`): being able to see the
# student is a different question from which of the student's activities the
# caller may see — `access.visible_activities`' own scoping still applies.
# ---------------------------------------------------------------------------


def test_a_trainer_sees_only_the_students_activities_on_batches_they_teach(
    admin_user, trainer_profile, trainer_profile_two, student_profile, enrollment, upcoming_batch
):
    """`trainer_profile` can see `student_profile` at all because the student
    has an enrolment on `batch`, which `trainer_profile` teaches
    (`students_access.visible_students`). That must not widen which of the
    student's *activities* they see: an activity recorded on the batch only
    `trainer_profile_two` teaches stays out of reach."""
    from apps.enrollments.services import enrol_student

    second_enrollment = enrol_student(
        student=student_profile, batch=upcoming_batch, actor=admin_user
    )

    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    mine = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
        assigned_to=trainer_profile.user,
    )
    theirs = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=second_enrollment,
        assigned_to=trainer_profile_two.user,
    )

    # Sanity: `trainer_profile` really can see the student profile itself.
    response = _client(trainer_profile.user).get(
        f"/api/v1/students/{student_profile.pk}/activities/"
    )
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert str(mine.pk) in ids
    assert str(theirs.pk) not in ids


# ---------------------------------------------------------------------------
# PATCH .../: `can_assign` says who may reassign, not who may *be* assigned —
# the same `allowed_assignee_roles` allowlist and `access.can_be_assigned`
# scope check `create_activity` enforces on this field must also hold when
# reassigning an already-open activity.
# ---------------------------------------------------------------------------


def test_patch_assigned_to_refuses_a_role_outside_the_type_allowlist(
    admin_user, student_profile, enrollment
):
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
    )
    response = _client(admin_user).patch(
        f"{ACTIVITIES}{activity.pk}/",
        {"assigned_to": str(student_profile.user.pk)},
        format="json",
    )
    assert response.status_code == 400
    activity.refresh_from_db()
    assert activity.assigned_to_id is None


def test_patch_assigned_to_refuses_a_trainer_outside_the_batch(
    admin_user, trainer_profile_two, student_profile, enrollment
):
    """`admin_user` (the creator) may reassign
    (`access.can_assign`), but `trainer_profile_two` does not teach
    `enrollment.batch` and holds no `activity.complete` capability — the same
    scope check that refuses them as a *create*-time assignee must also
    refuse them here."""
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
    )
    response = _client(admin_user).patch(
        f"{ACTIVITIES}{activity.pk}/",
        {"assigned_to": str(trainer_profile_two.user.pk)},
        format="json",
    )
    assert response.status_code == 400
    activity.refresh_from_db()
    assert activity.assigned_to_id is None


def test_patch_assigned_to_accepts_a_trainer_within_scope(
    admin_user, trainer_profile, student_profile, enrollment
):
    activity_type = _make_type(allowed_assignee_roles=["trainer"])
    activity = services.create_activity(
        actor=admin_user,
        student=student_profile,
        activity_type=activity_type,
        enrollment=enrollment,
    )
    response = _client(admin_user).patch(
        f"{ACTIVITIES}{activity.pk}/",
        {"assigned_to": str(trainer_profile.user.pk)},
        format="json",
    )
    assert response.status_code == 200
    activity.refresh_from_db()
    assert activity.assigned_to_id == trainer_profile.user.pk
