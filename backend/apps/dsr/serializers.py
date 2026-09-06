"""Daily status report serializers.

The read shape is one serializer for every audience — trainer, reviewer,
administrator — because nothing about a report's *content* is audience
dependent the way a submission's marks or an assignment's brief can be.
`access.py` already decided who may reach a given report; there is no second,
narrower shape hiding fields from someone who got this far.

Every nullable relation (`module`, `reviewed_by`) carries an explicit
``default=None`` on its derived field, following the pattern
`AssignmentSerializer` uses for the same reason: a plain `source="a.b"` raises
`AttributeError` through a null `a`, and DRF only swallows that when the field
has a default to fall back on. Skipping it would mean a draft report — which
has no reviewer yet — throwing a 500 the first time anyone read it.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictModelSerializer, StrictSerializer

from .models import DSR, DSRStatus

#: Decisions a reviewer may record. `DSRStatus.DRAFT` and `.SUBMITTED` are
#: deliberately absent — those are reached through `submit_dsr`, not review.
REVIEW_DECISION_CHOICES = [
    (DSRStatus.UNDER_REVIEW, DSRStatus.UNDER_REVIEW.label),
    (DSRStatus.APPROVED, DSRStatus.APPROVED.label),
    (DSRStatus.REJECTED, DSRStatus.REJECTED.label),
    (DSRStatus.REVISION_REQUIRED, DSRStatus.REVISION_REQUIRED.label),
]


class DSRSerializer(StrictModelSerializer):
    batch_code = serializers.CharField(source="batch.code", read_only=True)
    session_date = serializers.DateField(source="session.session_date", read_only=True)
    trainer_code = serializers.CharField(source="trainer.trainer_id", read_only=True)
    trainer_name = serializers.CharField(source="trainer.user.get_full_name", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True, default=None)
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True, default=None
    )
    is_editable = serializers.BooleanField(read_only=True)

    class Meta:
        model = DSR
        fields = (
            "id",
            "session",
            "session_date",
            "batch",
            "batch_code",
            "trainer",
            "trainer_code",
            "trainer_name",
            "report_date",
            "start_time",
            "end_time",
            "module",
            "module_title",
            "planned_topic",
            "actual_topic",
            "student_count",
            "present_count",
            "absent_count",
            "online_count",
            "offline_count",
            "teaching_notes",
            "issues",
            "student_concerns",
            "assignment_given",
            "assessment_conducted",
            "status",
            "is_editable",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "reviewed_by_name",
            "manager_comments",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DSRWriteSerializer(StrictSerializer):
    """Create and edit. ``status`` is absent — it moves only through
    :func:`services.submit_dsr` and :func:`services.review_dsr`.

    Every field is optional: starting a report prefills what it can from the
    register, and an edit only ever touches what changed, so a partial payload
    is the normal case rather than an exception the serializer has to allow
    for.

    ``submit`` exists because this is filled in at the end of class, not
    written up later — a trainer with nothing to correct on top of the
    prefilled numbers should not need a second request just to hand it over.
    It is not a model field: the view pops it off and calls
    :func:`services.submit_dsr` itself once the write it belongs to has gone
    through, so it can never be smuggled into a plain edit as if it were
    content.
    """

    submit = serializers.BooleanField(required=False, default=False)
    report_date = serializers.DateField(required=False)
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    module = serializers.UUIDField(required=False, allow_null=True)
    planned_topic = SafeCharField(max_length=250, required=False, allow_blank=True)
    actual_topic = SafeCharField(max_length=250, required=False, allow_blank=True)
    student_count = serializers.IntegerField(required=False, min_value=0)
    present_count = serializers.IntegerField(required=False, min_value=0)
    absent_count = serializers.IntegerField(required=False, min_value=0)
    online_count = serializers.IntegerField(required=False, min_value=0)
    offline_count = serializers.IntegerField(required=False, min_value=0)
    teaching_notes = SafeCharField(max_length=2000, required=False, allow_blank=True)
    issues = SafeCharField(max_length=2000, required=False, allow_blank=True)
    student_concerns = SafeCharField(max_length=2000, required=False, allow_blank=True)
    assignment_given = serializers.BooleanField(required=False)
    assessment_conducted = serializers.BooleanField(required=False)


class DSRReviewSerializer(StrictSerializer):
    """A reviewer's decision. See `services.review_dsr` for what each value does."""

    decision = serializers.ChoiceField(choices=REVIEW_DECISION_CHOICES)
    comments = SafeCharField(max_length=2000, required=False, allow_blank=True, default="")


class DSRDeleteSerializer(StrictSerializer):
    """A reason is required in practice even though the column allows blank —
    see `apps.common.deletion.soft_delete`."""

    reason = SafeCharField(max_length=255)
