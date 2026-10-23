"""A student's parents and guardians.

Two flat fields (`guardian_name`, `guardian_phone`) held one guardian with no
relation and no email. A real student often has two, and the messaging
settings ask whether a notice goes to the *first* guardian or to *all* of
them — a question two columns cannot answer.

What this suite fixes in place:

* the old pair is **copied, not moved**: a thousand real answers stay where
  they are, and the backfill is idempotent;
* exactly one guardian is primary, always, including when the form marks none;
* changing who the institute rings about money is `student.update_any`, never
  something the student does to their own record.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.common.exceptions import ApplicationError
from apps.students import services

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _url(student) -> str:
    return f"/api/v1/students/{student.pk}/guardians/"


def test_guardians_are_replaced_as_a_set(admin_user, student_profile):
    """The form shows them all at once and the counsellor edits them as a
    set, so what was sent is what there is."""
    services.set_guardians(
        actor=admin_user,
        student=student_profile,
        guardians=[
            {"name": "Ramesh Sharma", "relation": "father", "mobile": "+919876543210"},
            {"name": "Sunita Sharma", "relation": "mother"},
        ],
    )
    assert student_profile.guardians.count() == 2

    services.set_guardians(
        actor=admin_user,
        student=student_profile,
        guardians=[{"name": "Sunita Sharma", "relation": "mother"}],
    )
    assert [row.name for row in student_profile.guardians.all()] == ["Sunita Sharma"]


def test_exactly_one_guardian_is_the_first_one(admin_user, student_profile):
    """A student with guardians and no primary is a notice with nowhere to
    go, so the first row becomes it."""
    services.set_guardians(
        actor=admin_user,
        student=student_profile,
        guardians=[{"name": "Ramesh"}, {"name": "Sunita"}],
    )
    primaries = [row.name for row in student_profile.guardians.filter(is_primary=True)]
    assert primaries == ["Ramesh"]


def test_the_marked_one_is_the_first_one(admin_user, student_profile):
    services.set_guardians(
        actor=admin_user,
        student=student_profile,
        guardians=[
            {"name": "Ramesh"},
            {"name": "Sunita", "is_primary": True},
        ],
    )
    assert student_profile.guardians.filter(is_primary=True).get().name == "Sunita"
    # And only one, however many were ticked.
    assert student_profile.guardians.filter(is_primary=True).count() == 1


def test_two_ticked_still_leaves_one(admin_user, student_profile):
    services.set_guardians(
        actor=admin_user,
        student=student_profile,
        guardians=[
            {"name": "Ramesh", "is_primary": True},
            {"name": "Sunita", "is_primary": True},
        ],
    )
    assert student_profile.guardians.filter(is_primary=True).count() == 1


def test_a_guardian_needs_a_name(admin_user, student_profile):
    with pytest.raises(ApplicationError):
        services.set_guardians(
            actor=admin_user, student=student_profile, guardians=[{"name": "   "}]
        )
    assert student_profile.guardians.count() == 0


def test_the_api_reads_and_replaces(api_client_no_csrf, admin_user, student_profile):
    client = _client(admin_user)
    saved = client.put(
        _url(student_profile),
        {
            "guardians": [
                {
                    "name": "Ramesh Sharma",
                    "relation": "father",
                    "mobile": "+919876543210",
                    "email": "ramesh@example.test",
                    "occupation": "Shopkeeper",
                    "is_primary": True,
                }
            ]
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    body = saved.json()
    assert body[0]["relation_label"] == "Father"
    assert body[0]["is_primary"] is True

    read = client.get(_url(student_profile))
    assert [row["name"] for row in read.json()] == ["Ramesh Sharma"]


def test_a_student_reads_their_own_guardians_and_changes_none(
    api_client_no_csrf, admin_user, student_profile
):
    services.set_guardians(
        actor=admin_user, student=student_profile, guardians=[{"name": "Ramesh"}]
    )
    client = _client(student_profile.user)

    assert [row["name"] for row in client.get(_url(student_profile)).json()] == ["Ramesh"]
    refused = client.put(_url(student_profile), {"guardians": [{"name": "Nobody"}]}, format="json")
    assert refused.status_code == 403
    assert student_profile.guardians.get().name == "Ramesh"


def test_another_centres_manager_reaches_neither(
    api_client_no_csrf, admin_user, student_profile, other_branch_manager
):
    services.set_guardians(
        actor=admin_user, student=student_profile, guardians=[{"name": "Ramesh"}]
    )
    client = _client(other_branch_manager)
    assert client.get(_url(student_profile)).status_code == 404
    assert client.put(_url(student_profile), {"guardians": []}, format="json").status_code == 404


def test_a_classmate_cannot_read_a_students_guardians(
    api_client_no_csrf, admin_user, student_profile, other_student_profile
):
    services.set_guardians(
        actor=admin_user, student=student_profile, guardians=[{"name": "Ramesh"}]
    )
    response = _client(other_student_profile.user).get(_url(student_profile))
    assert response.status_code == 404


def test_a_trainer_who_teaches_them_reads_the_guardians_and_changes_none(
    api_client_no_csrf, admin_user, student_profile, trainer_profile, enrollment
):
    """A trainer reaches a student through the batch they teach, so they can
    see who to ring. Changing who the institute rings about money is a
    different right, and they do not hold it."""
    services.set_guardians(
        actor=admin_user, student=student_profile, guardians=[{"name": "Ramesh"}]
    )
    client = _client(trainer_profile.user)

    assert [row["name"] for row in client.get(_url(student_profile)).json()] == ["Ramesh"]
    refused = client.put(_url(student_profile), {"guardians": [{"name": "Nobody"}]}, format="json")
    assert refused.status_code == 403
    assert student_profile.guardians.get().name == "Ramesh"


def test_a_trainer_who_does_not_teach_them_reaches_nothing(
    api_client_no_csrf, trainer, student_profile
):
    assert _client(trainer).get(_url(student_profile)).status_code == 404


def test_the_backfill_copies_the_old_pair_and_leaves_it_alone(admin_user, student_profile):
    """`0014` copies `guardian_name`/`guardian_phone` into a row here. The
    columns keep their values: a student record that lost its only guardian's
    name to a confident migration is the worst kind of data loss.

    The migration's own function is run here, against the real model
    registry, rather than a reimplementation of what it does.
    """
    from importlib import import_module

    from django.apps import apps as django_apps

    backfill = import_module(
        "apps.students.migrations.0014_guardians_from_the_old_two_fields"
    ).copy_guardians

    student_profile.guardian_name = "Ramesh Sharma"
    student_profile.guardian_phone = "+919876543210"
    student_profile.save(update_fields=["guardian_name", "guardian_phone"])

    backfill(django_apps, None)

    student_profile.refresh_from_db()
    guardian = student_profile.guardians.get()
    assert guardian.name == "Ramesh Sharma"
    assert guardian.mobile == "+919876543210"
    assert guardian.is_primary is True
    # Copied, not moved.
    assert student_profile.guardian_name == "Ramesh Sharma"
    assert student_profile.guardian_phone == "+919876543210"

    # Idempotent: a re-run, or a dump already through it, makes no twins.
    backfill(django_apps, None)
    assert student_profile.guardians.count() == 1


def test_the_backfill_skips_a_student_with_no_guardian_recorded(admin_user, other_student_profile):
    from importlib import import_module

    from django.apps import apps as django_apps

    import_module("apps.students.migrations.0014_guardians_from_the_old_two_fields").copy_guardians(
        django_apps, None
    )

    assert other_student_profile.guardians.count() == 0
