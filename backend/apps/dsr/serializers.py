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


def _lesson_brief(lesson) -> dict:
    return {
        "id": str(lesson.pk),
        "title": lesson.title,
        "module": lesson.module.title if lesson.module_id else "",
    }


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
    is_done = serializers.BooleanField(read_only=True)
    is_overdue = serializers.SerializerMethodField()
    lessons_covered = serializers.SerializerMethodField()
    planned_lesson = serializers.SerializerMethodField()
    student_notes = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    homework_assignment_title = serializers.CharField(
        source="homework_assignment.title", read_only=True, default=None
    )
    extra_form = serializers.SerializerMethodField()

    def get_is_overdue(self, dsr: DSR) -> bool:
        from django.utils import timezone

        return bool(not dsr.is_done and dsr.due_at is not None and dsr.due_at < timezone.now())

    def get_lessons_covered(self, dsr: DSR) -> list[dict]:
        if dsr.pk is None or dsr._state.adding:
            # A preview has nothing saved yet; offer what `start_dsr` would.
            from apps.courses.models import Lesson

            from .services import recorded_lesson_id

            lesson_id = recorded_lesson_id(dsr.session) if dsr.session_id else None
            lesson = (
                Lesson.objects.filter(pk=lesson_id).select_related("module").first()
                if lesson_id
                else None
            )
            return [_lesson_brief(lesson)] if lesson is not None else []
        # `.all()` reads what `DSRQuerySet.with_related` prefetched; sorting
        # here keeps a list of reports at a fixed number of queries.
        lessons = sorted(
            dsr.lessons_covered.all(),
            key=lambda lesson: (lesson.module.position if lesson.module_id else 0, lesson.position),
        )
        return [_lesson_brief(lesson) for lesson in lessons]

    def get_planned_lesson(self, dsr: DSR) -> dict | None:
        lesson = dsr.session.planned_lesson if dsr.session_id else None
        return _lesson_brief(lesson) if lesson is not None else None

    def get_student_notes(self, dsr: DSR) -> list[dict]:
        if dsr.pk is None or dsr._state.adding:
            return []
        return [
            {
                "enrollment": str(note.enrollment_id),
                "student_name": note.enrollment.student.user.get_full_name()
                if note.enrollment.student.user_id
                else "",
                "flag": note.flag,
                "note": note.note,
            }
            for note in dsr.student_notes.all()
        ]

    def get_attachments(self, dsr: DSR) -> list[dict]:
        if dsr.pk is None or dsr._state.adding:
            return []
        return [
            {
                "upload": str(row.upload_id),
                "filename": row.upload.original_name,
                "caption": row.caption,
            }
            for row in dsr.attachments.all()
        ]

    def get_extra_form(self, dsr: DSR) -> dict | None:
        from apps.forms.serializers import FormFieldSerializer

        version = dsr.form_version
        if version is None and (dsr.pk is None or dsr._state.adding):
            from .services import extra_form_version

            version = extra_form_version()
        if version is None:
            return None
        fields = sorted(version.fields.all(), key=lambda field: field.order)
        return {
            "version": version.number,
            "fields": FormFieldSerializer(fields, many=True).data,
        }

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
            "topic_status",
            "lessons_covered",
            "planned_lesson",
            "homework",
            "homework_due_on",
            "homework_assignment",
            "homework_assignment_title",
            "student_notes",
            "attachments",
            "extra_form",
            "extra_answers",
            "due_at",
            "is_overdue",
            "is_done",
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
    topic_status = serializers.ChoiceField(
        choices=[
            ("completed", "Completed"),
            ("in_progress", "In progress"),
            ("skipped", "Skipped"),
        ],
        required=False,
    )
    homework = SafeCharField(max_length=2000, required=False, allow_blank=True)
    homework_due_on = serializers.DateField(required=False, allow_null=True)
    homework_assignment = serializers.UUIDField(required=False, allow_null=True)
    extra_answers = serializers.JSONField(required=False)
    #: Replaced as a whole when sent. Lesson ids from the batch's course.
    lessons_covered = serializers.ListField(child=serializers.UUIDField(), required=False)
    #: ``[{enrollment, flag, note}]``, replaced as a whole when sent.
    student_notes = serializers.ListField(child=serializers.DictField(), required=False)
    #: ``[{upload, caption}]``, replaced as a whole when sent.
    attachments = serializers.ListField(child=serializers.DictField(), required=False)


class DSRReviewSerializer(StrictSerializer):
    """A reviewer's decision. See `services.review_dsr` for what each value does."""

    decision = serializers.ChoiceField(choices=REVIEW_DECISION_CHOICES)
    comments = SafeCharField(max_length=2000, required=False, allow_blank=True, default="")


class DSRDeleteSerializer(StrictSerializer):
    """A reason is required in practice even though the column allows blank —
    see `apps.common.deletion.soft_delete`."""

    reason = SafeCharField(max_length=255)


class DSRCreateActivitySerializer(StrictSerializer):
    """ "Create an activity from this class" — a convenience wrapper around
    `apps.work.services.create_activity`, not a second creation path. The
    caller picks the student (from this class's own batch) and which kind of
    activity; everything else `create_activity` itself already validates
    (allowed creator/assignee roles, scope) applies unchanged."""

    activity_type = serializers.CharField(max_length=60)
    student = serializers.UUIDField()
    title = SafeCharField(max_length=160, required=False, allow_blank=True, default="")
    due_in_days = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=0
    )


class DSRHistorySerializer(serializers.Serializer):
    """One `AuditLog` row about this report — the "ChangeHistory" view
    `docs/erp/DATA_MODEL.md` describes: no table of its own, a queryset over
    `AuditLog` filtered by `resource_type`/`resource_id`, rendering
    `context["changes"]` (`{field: {from, to}}`) the way `update_dsr` and
    `review_dsr` already write it. Same shape `ActivityHistorySerializer`
    gives its own staff callers — id, actor, what happened, when."""

    id = serializers.UUIDField(read_only=True)
    action = serializers.CharField(read_only=True)
    actor = serializers.SerializerMethodField()
    context = serializers.JSONField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_actor(self, entry) -> dict | None:
        if entry.actor_id is None:
            return {"id": None, "name": entry.actor_label} if entry.actor_label else None
        return {"id": str(entry.actor_id), "name": entry.actor.get_full_name()}


class StudentClassNoteSerializer(serializers.Serializer):
    """What a student sees of a submitted class report: what was covered and
    the homework — never the trainer's notes, issues or concerns."""

    id = serializers.UUIDField(read_only=True)
    report_date = serializers.DateField(read_only=True)
    start_time = serializers.TimeField(read_only=True)
    batch_code = serializers.CharField(source="batch.code", read_only=True)
    trainer_name = serializers.CharField(source="trainer.user.get_full_name", read_only=True)
    topic = serializers.CharField(source="actual_topic", read_only=True)
    lessons_covered = serializers.SerializerMethodField()
    homework = serializers.CharField(read_only=True)
    homework_due_on = serializers.DateField(read_only=True, allow_null=True)
    homework_assignment = serializers.UUIDField(
        source="homework_assignment_id", read_only=True, allow_null=True
    )
    homework_assignment_title = serializers.CharField(
        source="homework_assignment.title", read_only=True, default=None
    )

    def get_lessons_covered(self, dsr: DSR) -> list[dict]:
        return [_lesson_brief(lesson) for lesson in dsr.lessons_covered.all()]
