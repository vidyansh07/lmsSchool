"""Activity engine API shapes (ERP Phase 9).

Read shapes are hand-shaped `Serializer`s with `SerializerMethodField`s
rather than `ModelSerializer`s, because almost every field a caller actually
wants (`student`, `type`, `assigned_to`, `form`, `history`) is a nested
summary of a related row, not a column on `Activity` itself — the same
reason `apps.forms.serializers.FormDefinitionSerializer` is hand-shaped
rather than model-derived. Write shapes are the project's usual
`StrictSerializer`s: unknown fields are rejected, not ignored.

Every foreign id here (`student`, `enrollment`, `activity_type`,
`assigned_to`) is a plain `UUIDField`, resolved in `views.py` against a
scoped queryset (`get_object_or_404(access.visible_students(user), pk=...)`
and friends) — never a `PrimaryKeyRelatedField` with an unscoped
`queryset=Model.objects.all()`, which would 403 an out-of-scope id instead
of 404ing it and leak that the id exists (rule 2).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.common.serializers import SafeCharField, StrictSerializer
from apps.forms.serializers import FormFieldSerializer

from .models import (
    Activity,
    ActivityCategory,
    ActivityPriority,
    ActivityResult,
    ActivityStatus,
    ActivityType,
    ActivityTypeStatus,
    RiskEffect,
)

# ---------------------------------------------------------------------------
# Activity types
# ---------------------------------------------------------------------------


class ActivityTypeSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    allowed_creator_roles = serializers.ListField(read_only=True)
    allowed_assignee_roles = serializers.ListField(read_only=True)
    visible_to_student = serializers.BooleanField(read_only=True)
    default_duration_minutes = serializers.IntegerField(read_only=True, allow_null=True)
    form = serializers.SerializerMethodField()
    requires_review = serializers.BooleanField(read_only=True)
    performance_weight = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True)
    risk_effect = serializers.CharField(read_only=True)
    reminder_minutes_before = serializers.IntegerField(read_only=True, allow_null=True)
    next_action = serializers.JSONField(read_only=True, allow_null=True)
    is_system = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_form(self, activity_type: ActivityType) -> str | None:
        return activity_type.form.slug if activity_type.form_id else None


class ActivityTypeCreateSerializer(StrictSerializer):
    slug = SafeCharField(max_length=60)
    name = SafeCharField(max_length=150)
    description = SafeCharField(required=False, allow_blank=True, default="")
    category = serializers.ChoiceField(choices=ActivityCategory.choices)
    allowed_creator_roles = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    allowed_assignee_roles = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    visible_to_student = serializers.BooleanField(required=False, default=False)
    default_duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1
    )
    #: The `FormDefinition` *slug*, not its id — matching what
    #: `ActivityTypeSerializer.get_form` returns, so a round trip (read,
    #: edit, write back) needs no id lookup on the client.
    form = serializers.CharField(required=False, allow_null=True, default=None, max_length=60)
    requires_review = serializers.BooleanField(required=False, default=False)
    performance_weight = serializers.DecimalField(
        max_digits=4, decimal_places=2, required=False, default=0
    )
    risk_effect = serializers.ChoiceField(
        choices=RiskEffect.choices, required=False, default=RiskEffect.NONE
    )
    reminder_minutes_before = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1
    )
    next_action = serializers.JSONField(required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(
        choices=ActivityTypeStatus.choices, required=False, default=ActivityTypeStatus.ACTIVE
    )


class ActivityTypePatchSerializer(StrictSerializer):
    """Every column except `slug` and `is_system` — both immutable via the API."""

    name = SafeCharField(max_length=150, required=False)
    description = SafeCharField(required=False, allow_blank=True)
    category = serializers.ChoiceField(choices=ActivityCategory.choices, required=False)
    allowed_creator_roles = serializers.ListField(child=serializers.CharField(), required=False)
    allowed_assignee_roles = serializers.ListField(child=serializers.CharField(), required=False)
    visible_to_student = serializers.BooleanField(required=False)
    default_duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    form = serializers.CharField(required=False, allow_null=True, max_length=60)
    requires_review = serializers.BooleanField(required=False)
    performance_weight = serializers.DecimalField(max_digits=4, decimal_places=2, required=False)
    risk_effect = serializers.ChoiceField(choices=RiskEffect.choices, required=False)
    reminder_minutes_before = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    next_action = serializers.JSONField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=ActivityTypeStatus.choices, required=False)


# ---------------------------------------------------------------------------
# Activities — write
# ---------------------------------------------------------------------------


class ActivityCreateSerializer(StrictSerializer):
    student = serializers.UUIDField()
    enrollment = serializers.UUIDField(required=False, allow_null=True, default=None)
    #: The `ActivityType`'s *slug* — its natural key everywhere else in this
    #: API (`/activity-types/{slug}/`, the list endpoint's `type` filter).
    activity_type = serializers.CharField(max_length=60)
    title = SafeCharField(max_length=160, required=False, allow_blank=True, default="")
    assigned_to = serializers.UUIDField(required=False, allow_null=True, default=None)
    planned_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    due_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    priority = serializers.ChoiceField(
        choices=ActivityPriority.choices, required=False, default=ActivityPriority.NORMAL
    )
    student_visible = serializers.BooleanField(required=False, allow_null=True, default=None)
    client_key = SafeCharField(max_length=100, required=False, allow_null=True, default=None)


class ActivityPatchSerializer(StrictSerializer):
    """Only while DRAFT/PLANNED/ASSIGNED — `views.py` enforces the status gate."""

    title = SafeCharField(max_length=160, required=False)
    planned_at = serializers.DateTimeField(required=False, allow_null=True)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=ActivityPriority.choices, required=False)
    assigned_to = serializers.UUIDField(required=False, allow_null=True)
    #: Only ever hides — never un-hides. `views.py` refuses `True`.
    student_visible = serializers.BooleanField(required=False)


class ActivityTransitionSerializer(StrictSerializer):
    to = serializers.ChoiceField(choices=ActivityStatus.choices)
    note = SafeCharField(required=False, allow_blank=True, default="")


class ActivityCompleteSerializer(StrictSerializer):
    form_values = serializers.JSONField(required=False, default=dict)
    summary = SafeCharField(required=False, allow_blank=True, default=None, allow_null=True)
    duration_minutes = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=0
    )
    completed_at = serializers.DateTimeField(required=False, allow_null=True, default=None)


class ActivityReviewSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=("approved", "requires_action"))
    note = SafeCharField(required=False, allow_blank=True, default="")


class ActivityDeleteSerializer(StrictSerializer):
    reason = SafeCharField(max_length=255)


# ---------------------------------------------------------------------------
# Activities — read
# ---------------------------------------------------------------------------


def _user_summary(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "name": user.get_full_name()}


def _student_summary(student) -> dict:
    return {
        "id": str(student.pk),
        "name": student.user.get_full_name() if student.user_id else "",
        "student_id": student.student_id,
    }


def _type_summary(activity_type: ActivityType) -> dict:
    return {
        "id": str(activity_type.pk),
        "slug": activity_type.slug,
        "name": activity_type.name,
        "category": activity_type.category,
    }


def _batch_summary(batch) -> dict | None:
    if batch is None:
        return None
    return {"id": str(batch.pk), "code": batch.code, "name": batch.name}


class ActivityListSerializer(serializers.Serializer):
    """One row of `GET /activities/`. Never form values — detail only."""

    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    priority = serializers.CharField(read_only=True)
    planned_at = serializers.DateTimeField(read_only=True, allow_null=True)
    due_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    student = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    batch = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()

    def get_student(self, activity: Activity) -> dict:
        return _student_summary(activity.student)

    def get_type(self, activity: Activity) -> dict:
        return _type_summary(activity.activity_type)

    def get_batch(self, activity: Activity) -> dict | None:
        return _batch_summary(activity.batch)

    def get_assigned_to(self, activity: Activity) -> dict | None:
        return _user_summary(activity.assigned_to)

    def get_created_by(self, activity: Activity) -> dict | None:
        return _user_summary(activity.created_by)

    def get_counts(self, activity: Activity) -> dict:
        history_count = getattr(activity, "history_count", None)
        if history_count is None:
            history_count = activity.history.count()
        return {"history": history_count}


class ActivityHistorySerializer(serializers.Serializer):
    """`note`, `changes` and `actor` are free-text staff commentary and
    provenance — cancellation/reopen reasons, a review's `requires_action`
    note, a completion's raw score — never vetted against any
    `visible_to_student` flag the way `form`/`form_values` are. A student
    caller (`context["as_student"]`) gets only the bare status transition,
    the same reduction `get_form`/`get_form_values` already give the rest of
    the detail response."""

    id = serializers.UUIDField(read_only=True)
    actor = serializers.SerializerMethodField()
    from_status = serializers.CharField(read_only=True)
    to_status = serializers.CharField(read_only=True)
    note = serializers.SerializerMethodField()
    changes = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def _as_student(self) -> bool:
        return bool(self.context.get("as_student"))

    def get_actor(self, entry) -> dict | None:
        if self._as_student():
            return None
        return _user_summary(entry.actor)

    def get_note(self, entry) -> str:
        return "" if self._as_student() else entry.note

    def get_changes(self, entry) -> dict:
        return {} if self._as_student() else entry.changes


class ActivityDetailSerializer(ActivityListSerializer):
    """Adds everything the list row omits: the pinned form, this caller's
    view of the submitted values, history, provenance."""

    enrollment = serializers.SerializerMethodField()
    summary = serializers.CharField(read_only=True)
    review_note = serializers.CharField(read_only=True)
    result = serializers.CharField(read_only=True)
    score = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True, allow_null=True
    )
    max_score = serializers.DecimalField(
        max_digits=5, decimal_places=2, read_only=True, allow_null=True
    )
    duration_minutes = serializers.IntegerField(read_only=True, allow_null=True)
    student_visible = serializers.BooleanField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    reviewed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    performed_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()
    form = serializers.SerializerMethodField()
    form_values = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()
    parent = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    automation_run = serializers.SerializerMethodField()
    available_transitions = serializers.SerializerMethodField()

    def to_representation(self, activity: Activity) -> dict:
        data = super().to_representation(activity)
        if self._as_student():
            # `review_note` is free-text reviewer commentary — the same kind
            # of staff-only content `ActivityHistorySerializer` withholds
            # from a student caller, and no `visible_to_student` flag exists
            # for it to be paired against.
            data["review_note"] = ""
            if not self._score_visible(activity):
                data["score"] = None
                data["max_score"] = None
                data["result"] = ActivityResult.N_A
        return data

    def _score_visible(self, activity: Activity) -> bool:
        """Whether a student may see this activity's derived `score`,
        `max_score` and `result`. `services._extract_score` derives all
        three from one specific form field — the field flagged with a
        `performance_key` — via `FormVersion.performance_field()`. Nothing
        in `complete_activity` requires *that* field itself to be
        `visible_to_student`, so this checks it explicitly rather than
        trusting a type author to have paired the two flags; `result` is
        gated the same way `score`/`max_score` are because it is derived
        from them and would otherwise leak the same information back
        (pass/fail against a hidden number)."""
        if activity.form_version_id is None:
            return True
        field = activity.form_version.performance_field()
        return field is not None and field.visible_to_student

    def get_enrollment(self, activity: Activity) -> str | None:
        return str(activity.enrollment_id) if activity.enrollment_id else None

    def get_performed_by(self, activity: Activity) -> dict | None:
        return _user_summary(activity.performed_by)

    def get_reviewed_by(self, activity: Activity) -> dict | None:
        return _user_summary(activity.reviewed_by)

    def _as_student(self) -> bool:
        return bool(self.context.get("as_student"))

    def get_form(self, activity: Activity) -> dict | None:
        if activity.form_version_id is None:
            return None
        fields = activity.form_version.fields.all()
        if self._as_student():
            fields = [field for field in fields if field.visible_to_student]
        return {
            "version": activity.form_version.number,
            "fields": FormFieldSerializer(fields, many=True).data,
        }

    def get_form_values(self, activity: Activity) -> dict | None:
        if activity.form_response_id is None:
            return None
        values = activity.form_response.values or {}
        if not self._as_student():
            return values
        visible_keys = (
            {field.key for field in activity.form_version.fields.all() if field.visible_to_student}
            if activity.form_version_id
            else set()
        )
        return {key: value for key, value in values.items() if key in visible_keys}

    def get_history(self, activity: Activity) -> list[dict]:
        return ActivityHistorySerializer(
            activity.history.select_related("actor"), many=True, context=self.context
        ).data

    def get_parent(self, activity: Activity) -> str | None:
        return str(activity.parent_id) if activity.parent_id else None

    def get_children(self, activity: Activity) -> list[dict]:
        # Nothing populates `parent` yet (Phase 14), so this is an empty list
        # in practice today — but shaped like a list-row summary, not bare
        # ids, for whenever it is not.
        return ActivityListSerializer(activity.children.with_related(), many=True).data

    def get_automation_run(self, activity: Activity) -> str | None:
        # The FK does not exist until Phase 14 adds it additively. Explicit
        # `null` keeps the contract shape stable for the frontend today.
        return None

    def get_available_transitions(self, activity: Activity) -> list[str]:
        """The `to` values currently legal from `POST .../transition/` for
        this activity — never includes `completed`/`under_review`, which
        only `/complete/` and the system itself may set."""
        from .transitions import legal_targets

        return sorted(legal_targets(activity.status))


__all__ = [
    "ActivityCompleteSerializer",
    "ActivityCreateSerializer",
    "ActivityDeleteSerializer",
    "ActivityDetailSerializer",
    "ActivityHistorySerializer",
    "ActivityListSerializer",
    "ActivityPatchSerializer",
    "ActivityReviewSerializer",
    "ActivityTransitionSerializer",
    "ActivityTypeCreateSerializer",
    "ActivityTypePatchSerializer",
    "ActivityTypeSerializer",
]
