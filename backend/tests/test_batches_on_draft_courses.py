"""A batch may run any course that has not been archived.

Publishing decides whether a course shows in the catalogue; it is not a gate
on teaching it. Requiring a published lesson before a batch could be created
made planning wait on authoring, which is the wrong way round.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.batches.services import create_batch
from apps.courses import services as course_services
from apps.courses.models import PublishStatus


def _create(course, admin_user, trainer_profile):
    today = timezone.localdate()
    return create_batch(
        actor=admin_user,
        name="Planned ahead",
        course=course,
        trainer=trainer_profile,
        start_date=today + timedelta(days=14),
        end_date=today + timedelta(days=74),
        capacity=20,
    )


@pytest.mark.django_db
def test_a_draft_course_can_have_a_batch(admin_user, draft_course, trainer_profile):
    assert draft_course.status == PublishStatus.DRAFT
    batch = _create(draft_course, admin_user, trainer_profile)
    assert batch.course_id == draft_course.pk


@pytest.mark.django_db
def test_an_archived_course_cannot(admin_user, published_course, trainer_profile):
    course_services.set_course_status(
        course=published_course, target=PublishStatus.ARCHIVED, actor=admin_user, may_publish=True
    )
    published_course.refresh_from_db()
    with pytest.raises(ValidationError) as refused:
        _create(published_course, admin_user, trainer_profile)
    assert "archived" in str(refused.value).lower()
