"""Fee endpoints.

Reading a fee is for whoever may see the enrolment: staff with `fee.view_any`,
or the student it belongs to. Changing one is `fee.manage_any` — counsellors
and managers — and the services check that again, so the permission lives in
one place even if a view is wired wrong.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import has_capability
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.enrollments.models import Enrollment
from apps.students.models import StudentProfile

from . import services
from .models import FeePayment, FeePlan
from .serializers import (
    FeeHistoryEntrySerializer,
    FeePaymentSerializer,
    FeePlanBriefSerializer,
    FeePlanSerializer,
    FeesOverviewSerializer,
    RecordPaymentSerializer,
    SetFeePlanSerializer,
    SetNextDueSerializer,
    StudentFeeSummarySerializer,
    VoidPaymentSerializer,
)

FEES_TAG = ["Fees"]


def _enrollment(enrollment_id) -> Enrollment:
    return get_object_or_404(
        Enrollment.objects.select_related("student__user", "batch", "course"), pk=enrollment_id
    )


def _may_read(user, enrollment: Enrollment) -> bool:
    if has_capability(user, Capability.FEE_VIEW_ANY):
        return True
    return enrollment.student.user_id == user.pk


def _plan_or_404(enrollment: Enrollment) -> FeePlan:
    return get_object_or_404(
        FeePlan.objects.select_related("enrollment__batch", "enrollment__course").with_totals(),
        enrollment=enrollment,
    )


class EnrollmentFeeView(APIView):
    """The fee for one enrolment: read it, or set it."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="The fee agreed for an enrolment, with its payments",
        responses={200: FeePlanSerializer, 404: OpenApiResponse(description="No fee set yet.")},
        tags=FEES_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment(enrollment_id)
        if not _may_read(request.user, enrollment):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(FeePlanSerializer(_plan_or_404(enrollment)).data)

    @extend_schema(
        summary="Set or change the fee agreed for an enrolment",
        request=SetFeePlanSerializer,
        responses={200: FeePlanSerializer},
        tags=FEES_TAG,
    )
    def put(self, request, enrollment_id):
        if not has_capability(request.user, Capability.FEE_MANAGE_ANY):
            return Response(status=status.HTTP_403_FORBIDDEN)
        enrollment = _enrollment(enrollment_id)
        serializer = SetFeePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_fee_plan(
            enrollment=enrollment, actor=request.user, **serializer.validated_data
        )
        return Response(FeePlanSerializer(_plan_or_404(enrollment)).data)


class EnrollmentFeeNextDueView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Set what is expected next, and by when",
        request=SetNextDueSerializer,
        responses={200: FeePlanSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = _enrollment(enrollment_id)
        plan = _plan_or_404(enrollment)
        serializer = SetNextDueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_next_due(
            plan=plan,
            actor=request.user,
            amount=serializer.validated_data.get("next_due_amount"),
            on=serializer.validated_data.get("next_due_on"),
        )
        return Response(FeePlanSerializer(_plan_or_404(enrollment)).data)


class EnrollmentFeePaymentsView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Record a payment against an enrolment's fee",
        request=RecordPaymentSerializer,
        responses={201: FeePaymentSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = _enrollment(enrollment_id)
        plan = _plan_or_404(enrollment)
        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = services.record_payment(
            plan=plan, actor=request.user, **serializer.validated_data
        )
        return Response(FeePaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class FeePaymentVoidView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Void a payment that was recorded by mistake",
        request=VoidPaymentSerializer,
        responses={200: FeePaymentSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, payment_id):
        payment = get_object_or_404(
            FeePayment.objects.select_related(
                "plan__enrollment__student", "plan__enrollment__batch"
            ),
            pk=payment_id,
        )
        serializer = VoidPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.void_payment(
            payment=payment, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(FeePaymentSerializer(payment).data)


class EnrollmentFeeHistoryView(APIView):
    """Who changed what, when — the audit rows for this enrolment's fee."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Every change to an enrolment's fee, newest first",
        responses={200: FeeHistoryEntrySerializer(many=True)},
        tags=FEES_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment(enrollment_id)
        if not _may_read(request.user, enrollment):
            return Response(status=status.HTTP_403_FORBIDDEN)
        rows = [
            {
                "id": entry.pk,
                "action": entry.action,
                "action_label": entry.get_action_display(),
                "actor_label": entry.actor_label
                or (entry.actor.email if entry.actor else "system"),
                "created_at": entry.created_at,
                "context": entry.context,
            }
            for entry in services.fee_history(enrollment)[:200]
        ]
        return Response(FeeHistoryEntrySerializer(rows, many=True).data)


class StudentFeesView(APIView):
    """Everything a student owes and has paid, across their courses."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="A student's fees across every course",
        responses={200: StudentFeeSummarySerializer},
        tags=FEES_TAG,
    )
    def get(self, request, student_id):
        student = get_object_or_404(StudentProfile.objects.select_related("user"), pk=student_id)
        if (
            not has_capability(request.user, Capability.FEE_VIEW_ANY)
            and student.user_id != request.user.pk
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(StudentFeeSummarySerializer(services.student_fee_summary(student)).data)


class MyFeesView(APIView):
    """The signed-in student's own fees."""

    permission_classes = (IsActiveUser,)

    @extend_schema(summary="My fees", responses={200: StudentFeeSummarySerializer}, tags=FEES_TAG)
    def get(self, request):
        student = getattr(request.user, "student_profile", None)
        if student is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(StudentFeeSummarySerializer(services.student_fee_summary(student)).data)


class FeesOverviewView(APIView):
    """The counsellor's fees panel."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY

    @extend_schema(
        summary="Collections, overdue and unpaid, at a glance",
        responses={200: FeesOverviewSerializer},
        tags=FEES_TAG,
    )
    def get(self, request):
        overview = services.fees_overview()
        for key in ("overdue", "due_soon"):
            rows = FeePlanBriefSerializer(overview[key], many=True).data
            for row, plan in zip(rows, overview[key], strict=True):
                user = plan.enrollment.student.user
                row["student_id"] = str(plan.enrollment.student_id)
                row["student_name"] = user.full_name or user.email
            overview[key] = rows
        return Response(FeesOverviewSerializer(overview).data)
