"""Student endpoints (``/api/v1/students/``).

Two access paths, deliberately separate:

* ``/students/me/`` — a student's own record. No identifier in the URL, so
  there is nothing to tamper with.
* ``/students/<id>/`` — administrator access, gated on a capability, plus an
  object-level check so a student who guesses another student's id gets 403
  rather than someone else's data.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import UserRole, has_capability
from apps.common.caching import MINUTE, remember
from apps.common.exceptions import AuthorityError
from apps.common.permissions import Capability, HasCapability, IsActiveUser, IsOwnerOrHasCapability
from apps.fees.queries import annotate_student_fee_totals
from apps.organisation.access import resolve_submitted_branch
from apps.work.serializers import ActivityDetailSerializer

from . import access, services, student_360
from .models import StudentProfile
from .serializers import (
    AdminStudentProfileSerializer,
    AdminStudentUpdateSerializer,
    FeeAmountUpdateSerializer,
    FeeStatusUpdateSerializer,
    FollowUpCreateSerializer,
    StudentCreateSerializer,
    StudentDuplicateSerializer,
    StudentDuplicatesResponseSerializer,
    StudentListSerializer,
    StudentProfileSerializer,
    StudentSelfUpdateSerializer,
)

STUDENTS_TAG = ["students"]


class StudentFilterSet(django_filters.FilterSet):
    fee_status = django_filters.CharFilter(field_name="fee_status", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="user__is_active")
    qualification = django_filters.CharFilter(field_name="qualification", lookup_expr="exact")
    city = django_filters.CharFilter(field_name="city", lookup_expr="iexact")
    # "Everyone from Infosys" — the question a referral scheme starts with.
    institution = django_filters.CharFilter(field_name="institution", lookup_expr="icontains")
    institution_kind = django_filters.CharFilter(field_name="institution_kind", lookup_expr="exact")
    referred_by = django_filters.UUIDFilter(field_name="referred_by_id")
    branch = django_filters.UUIDFilter(field_name="branch_id")

    class Meta:
        model = StudentProfile
        fields = (
            "fee_status",
            "qualification",
            "city",
            "institution",
            "institution_kind",
            "referred_by",
            "branch",
        )


class StudentListCreateView(ListCreateAPIView):
    """Administrator listing and creation."""

    permission_classes = (HasCapability,)
    capability_map = {
        "GET": Capability.STUDENT_VIEW_ANY,
        "POST": Capability.STUDENT_CREATE,
    }
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = StudentFilterSet
    search_fields = (
        "student_id",
        "roll_number",
        "user__email",
        "user__first_name",
        "user__last_name",
        "institution",
    )
    ordering_fields = ("student_id", "created_at", "fee_status", "user__email")
    ordering = ("-created_at",)
    serializer_class = StudentListSerializer

    def get_queryset(self):
        # The ledger's totals ride on the *visible* queryset, so a bounded
        # caller's list carries paid/balance for their own centre's students
        # and never resolves anybody else's.
        return annotate_student_fee_totals(
            access.visible_students(self.request.user).select_related(
                "fee_amount_updated_by", "referred_by__user"
            )
        )

    @extend_schema(
        summary="List students", responses={200: StudentListSerializer}, tags=STUDENTS_TAG
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Create a student",
        request=StudentCreateSerializer,
        responses={
            201: AdminStudentProfileSerializer,
            409: OpenApiResponse(description="Email already in use."),
        },
        tags=STUDENTS_TAG,
    )
    def post(self, request, *args, **kwargs):
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        profile_fields = data.pop("profile", None) or {}
        # The service re-checks that this actor may quote a fee; the view's
        # capability is `student.create`, which is not the same permission.
        # It also re-runs its own duplicate check against `email`/`phone`
        # (Phase 17) rather than trusting `override_reason`'s mere presence.
        branch = resolve_submitted_branch(request.user, data.pop("branch", None))
        profile = services.create_student(
            actor=request.user, branch=branch, profile_fields=profile_fields, **data
        )
        return Response(AdminStudentProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class StudentDuplicatesView(APIView):
    """ "Does anyone match?" — `USER_JOURNEYS.md` §4.2, asked by the
    registration wizard as soon as email or phone is complete.

    A read, not a search: resolved entirely through
    `services.find_duplicate_candidates`, which narrows through
    `access.visible_students` — the same disclosure-safe queryset Phase 11's
    global search and the Student 360 route both go through — so a match
    outside the caller's own reach (another branch, or simply a record this
    role cannot see) is not returned at all, never a redacted stub. Gated on
    `student.create`, the same capability the registration wizard itself
    requires to reach this step — never a laxer, separate gate for what is,
    in effect, a way to probe for a student's existence.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.STUDENT_CREATE

    @extend_schema(
        summary="Check for a matching student mid-registration",
        parameters=[
            OpenApiParameter("email", str, required=False),
            OpenApiParameter("phone", str, required=False),
            OpenApiParameter(
                "name",
                str,
                required=False,
                description=(
                    "Accepted for the wizard's own contract; matching is exact "
                    "email/phone only (never by name — see the journey's own wording)."
                ),
            ),
        ],
        responses={200: StudentDuplicatesResponseSerializer},
        tags=STUDENTS_TAG,
    )
    def get(self, request):
        matches = services.find_duplicate_candidates(
            user=request.user,
            email=request.query_params.get("email", ""),
            phone=request.query_params.get("phone", ""),
        )[: services.DUPLICATE_MATCH_LIMIT]
        return Response({"results": StudentDuplicateSerializer(matches, many=True).data})


class StudentFollowUpView(APIView):
    """ "Plan a follow-up" on a student's record (`USER_JOURNEYS.md` §4.3).

    A thin wrapper around `apps.work.services.create_activity` — the same
    shape `apps.dsr.views.DSRCreateActivityView` uses for its own "create an
    activity from this class" action (Phase 15) — never a direct
    `Activity.objects.create()`, so this inherits that function's own
    allowed-creator/-assignee-role and scope checks unchanged, and its own
    audit write.

    ``channel`` is deliberately absent from this endpoint's body. The seeded
    ``follow-up-note`` form (`FORM_CATALOG.md`) already has a required
    `channel` field, captured when the follow-up is later completed through
    Phase 9's existing form pipeline — the point at which a channel is
    actually known, not before the call has even happened. Adding a second,
    earlier `channel` field here would be a field the data model was never
    given, not a shortcut around it.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Plan a follow-up for a student",
        request=FollowUpCreateSerializer,
        responses={201: ActivityDetailSerializer},
        tags=STUDENTS_TAG,
    )
    def post(self, request, student_id):
        student = get_object_or_404(access.visible_students(request.user), pk=student_id)

        serializer = FollowUpCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from apps.enrollments.models import Enrollment
        from apps.work import access as work_access
        from apps.work import services as work_services
        from apps.work.models import ActivityType

        # The student's own most recent enrolment, whatever its status — a
        # follow-up is not scoped to one class the way `DSRCreateActivityView`'s
        # is, and a student still awaiting a batch has none at all, which
        # `create_activity` already handles by falling back to the student's
        # own branch.
        enrollment = Enrollment.objects.filter(student=student).order_by("-created_at").first()
        activity_type = get_object_or_404(ActivityType.objects.all(), slug="follow-up")

        activity = work_services.create_activity(
            actor=request.user,
            student=student,
            activity_type=activity_type,
            enrollment=enrollment,
            # Self-assigned to whoever is planning it. `create_activity`'s own
            # `validate_assignee` still enforces the type's allowed-assignee
            # roles unchanged — a manager may create a follow-up (the
            # catalog's creator list) but is not one of its assignees, so a
            # manager calling this endpoint is refused here exactly as
            # `POST /activities/` would refuse the same assignment.
            assigned_to=request.user,
            due_at=data["due_at"],
            priority=data.get("priority"),
        )
        detail = get_object_or_404(work_access.visible_activities(request.user), pk=activity.pk)
        return Response(
            ActivityDetailSerializer(detail, context={"as_student": False}).data,
            status=status.HTTP_201_CREATED,
        )


class StudentDetailView(RetrieveUpdateAPIView):
    """Retrieve or update one student record.

    Object-level ownership is checked on every request. A student may read and
    edit their own record here; anyone else needs the administrator capability.
    """

    permission_classes = (IsOwnerOrHasCapability,)
    object_capability = Capability.STUDENT_VIEW_ANY
    lookup_url_kwarg = "student_id"

    def get_queryset(self):
        # The branch, and only the branch: `IsOwnerOrHasCapability` still
        # answers the audience question, and it answers it with a 403.
        return access.reachable_students(self.request.user)

    def get_object(self):
        profile = get_object_or_404(self.get_queryset(), pk=self.kwargs["student_id"])
        self.check_object_permissions(self.request, profile)
        return profile

    def _is_admin(self) -> bool:
        return has_capability(self.request.user, Capability.STUDENT_VIEW_ANY)

    def get_serializer_class(self):
        if self.request.method == "GET":
            return AdminStudentProfileSerializer if self._is_admin() else StudentProfileSerializer
        return AdminStudentUpdateSerializer if self._is_admin() else StudentSelfUpdateSerializer

    @extend_schema(summary="Retrieve a student", tags=STUDENTS_TAG)
    def get(self, request, *args, **kwargs):
        profile = self.get_object()
        return Response(self.get_serializer_class()(profile).data)

    @extend_schema(summary="Update a student", tags=STUDENTS_TAG)
    def patch(self, request, *args, **kwargs):
        profile = self.get_object()
        # Editing someone else's record needs the update capability, not just
        # the read capability that got the caller this far.
        is_admin_edit = has_capability(request.user, Capability.STUDENT_UPDATE_ANY)
        if profile.user_id != request.user.pk and not is_admin_edit:
            return Response(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": "You may only edit your own profile.",
                        "request_id": getattr(request, "request_id", "-"),
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer_class = (
            AdminStudentUpdateSerializer if is_admin_edit else StudentSelfUpdateSerializer
        )
        allowed = (
            serializer_class.Meta.fields if is_admin_edit else StudentProfile.SELF_EDITABLE_FIELDS
        )
        serializer = serializer_class(instance=profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_student_profile(
            profile=profile,
            actor=request.user,
            allowed_fields=tuple(allowed),
            **serializer.validated_data,
        )
        read_class = AdminStudentProfileSerializer if is_admin_edit else StudentProfileSerializer
        return Response(read_class(updated).data)


class StudentMeView(APIView):
    """The signed-in student's own profile.

    No identifier in the URL: the record is resolved from the session, so there
    is nothing for a caller to tamper with.
    """

    permission_classes = (IsActiveUser,)

    def _profile(self, request) -> StudentProfile:
        if request.user.role != UserRole.STUDENT:
            raise PermissionDenied("This endpoint is only available to student accounts.")
        return services.get_or_create_profile_for(request.user)

    @extend_schema(
        summary="Own student profile", responses={200: StudentProfileSerializer}, tags=STUDENTS_TAG
    )
    def get(self, request):
        return Response(StudentProfileSerializer(self._profile(request)).data)

    @extend_schema(
        summary="Update own student profile",
        request=StudentSelfUpdateSerializer,
        responses={200: StudentProfileSerializer},
        tags=STUDENTS_TAG,
    )
    def patch(self, request):
        profile = self._profile(request)
        serializer = StudentSelfUpdateSerializer(instance=profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_student_profile(
            profile=profile,
            actor=request.user,
            allowed_fields=StudentProfile.SELF_EDITABLE_FIELDS,
            **serializer.validated_data,
        )
        return Response(StudentProfileSerializer(updated).data)


class StudentFeeAmountView(APIView):
    """Set or clear the fee agreed with a student.

    The same capability as the status — a counsellor or manager who may say a
    fee is paid may say what it was — and, like the status, always audited.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.STUDENT_SET_FEE_STATUS

    @extend_schema(
        summary="Set a student's agreed fee",
        request=FeeAmountUpdateSerializer,
        responses={200: AdminStudentProfileSerializer},
        tags=STUDENTS_TAG,
    )
    def post(self, request, student_id):
        profile = get_object_or_404(access.visible_students(request.user), pk=student_id)
        serializer = FeeAmountUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_fee_amount(
            profile=profile,
            fee_amount=serializer.validated_data["fee_amount"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(AdminStudentProfileSerializer(updated).data)


class StudentFeeStatusView(APIView):
    """Change a student's fee status. Administrator-only and always audited."""

    permission_classes = (HasCapability,)
    required_capability = Capability.STUDENT_SET_FEE_STATUS

    @extend_schema(
        summary="Set a student's fee status",
        request=FeeStatusUpdateSerializer,
        responses={200: AdminStudentProfileSerializer},
        tags=STUDENTS_TAG,
    )
    def post(self, request, student_id):
        profile = get_object_or_404(access.visible_students(request.user), pk=student_id)
        serializer = FeeStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.set_fee_status(
            profile=profile,
            fee_status=serializer.validated_data["fee_status"],
            actor=request.user,
            note=serializer.validated_data.get("note", ""),
        )
        return Response(AdminStudentProfileSerializer(updated).data)


class Student360View(APIView):
    """`GET /students/{id}/360/` (ERP Phase 11) — one call for the Student 360
    screen. Permission is exactly `StudentDetailView`'s/
    `StudentActivityListView`'s rule, reused rather than reinvented:
    `reachable_students` (branch) narrows first, so a cross-branch id 404s,
    then `can_view_student` (audience) decides, so a same-branch classmate a
    student may not read 403s instead of either collapsing into the other.

    Cached for a minute, keyed on `(student, viewer_scope_key)` — never just
    the student id, or the first caller to warm the cache would leak their
    view's shape (which activities, which counts) to a caller with a
    different, narrower reach. See `student_360.viewer_scope_key` for why
    that key is safe to share within a tier and never across one.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Student 360",
        responses={200: OpenApiResponse(description="The Student 360 read model.")},
        tags=STUDENTS_TAG,
    )
    def get(self, request, student_id):
        student = get_object_or_404(access.reachable_students(request.user), pk=student_id)
        if not access.can_view_student(request.user, student):
            raise AuthorityError("You do not have authority to see this student.")

        scope_key = student_360.viewer_scope_key(request.user)
        # Prefix carries the student id (`student_360.forget_360` bumps
        # exactly this prefix on a write), so `parts` only needs the
        # viewer's scope key — see `student_360.PREFIX`'s own docstring.
        data = remember(
            f"{student_360.PREFIX}:{student.pk}",
            (scope_key,),
            MINUTE,
            lambda: student_360.build(request.user, student),
        )
        return Response(data)
