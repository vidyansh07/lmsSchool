"""Fee endpoints.

Reading a fee is for whoever may see the enrolment: staff with `fee.view_any`,
or the student it belongs to. Changing one is `fee.manage_any` — counsellors
and managers — and the services check that again, so the permission lives in
one place even if a view is wired wrong.

Every record is resolved inside the caller's *visible* queryset
(`apps.batches.access.visible_enrollments`, `apps.students.access.visible_students`)
rather than the model manager, so a counsellor at one centre asking for an
enrolment at another gets the same 404 a guessed id gets, and the overview
totals are about their centre and nobody else's.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import has_capability
from apps.batches import access as batch_access
from apps.common.caching import MINUTE, remember
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.enrollments.models import Enrollment
from apps.students import access as students_access

from . import services
from .models import FeePayment, FeePlan
from .serializers import (
    FeeCollectionsTrendPointSerializer,
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


def _enrollment(user, enrollment_id) -> Enrollment:
    return get_object_or_404(
        batch_access.visible_enrollments(user).select_related("student__user", "batch", "course"),
        pk=enrollment_id,
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
        enrollment = _enrollment(request.user, enrollment_id)
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
        enrollment = _enrollment(request.user, enrollment_id)
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
        enrollment = _enrollment(request.user, enrollment_id)
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
        enrollment = _enrollment(request.user, enrollment_id)
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
            FeePayment.objects.filter(
                plan__enrollment__in=batch_access.visible_enrollments(request.user)
            ).select_related("plan__enrollment__student", "plan__enrollment__batch"),
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
        enrollment = _enrollment(request.user, enrollment_id)
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
        student = get_object_or_404(students_access.visible_students(request.user), pk=student_id)
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


class FeeCollectionsTrendView(APIView):
    """Collections per week, for the fees chart.

    Declared with `required_capability` rather than checked in the body, so
    `tests/test_authorization_matrix.py` -- which reads that attribute off
    the view class -- sweeps this route for every role automatically.

    Uncached, deliberately. `fees/overview/` is cached for a minute and
    `services._forget_overviews()` exists to invalidate it; a second cached
    prefix is a second thing that invalidation has to remember, and a
    collections chart that does not move after a payment is recorded is a
    support ticket. If it is ever cached, the key needs the caller and the
    `weeks` window in it -- a key without `weeks` serves the 52-week payload
    to a 4-week request, which is a wrong chart with no error anywhere.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY

    @extend_schema(
        summary="Fee collections by week",
        parameters=[OpenApiParameter("weeks", int)],
        responses={200: FeeCollectionsTrendPointSerializer(many=True)},
        tags=FEES_TAG,
    )
    def get(self, request):
        weeks = max(1, min(52, int(request.query_params.get("weeks", 12))))
        rows = services.fee_collections_trend(user=request.user, weeks=weeks)
        return Response(FeeCollectionsTrendPointSerializer(rows, many=True).data)


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
        def build():
            overview = services.fees_overview(user=request.user)
            for key in ("overdue", "due_soon"):
                rows = FeePlanBriefSerializer(overview[key], many=True).data
                for row, plan in zip(rows, overview[key], strict=True):
                    user = plan.enrollment.student.user
                    row["student_id"] = str(plan.enrollment.student_id)
                    row["student_name"] = user.full_name or user.email
                overview[key] = rows
            return FeesOverviewSerializer(overview).data

        return Response(remember("fees:overview", (request.user.pk,), MINUTE, build))


class FeePaymentReceiptView(APIView):
    """The receipt for one payment, as a PDF. Staff who can see the enrolment,
    or the student it belongs to."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download the receipt for a payment",
        responses={200: OpenApiResponse(description="A PDF.")},
        tags=FEES_TAG,
    )
    def get(self, request, payment_id):
        from django.http import HttpResponse

        from apps.configuration.settings_resolver import effective_settings

        from .receipts import render_receipt_pdf

        payment = get_object_or_404(
            FeePayment.objects.filter(
                plan__enrollment__in=batch_access.visible_enrollments(request.user)
            ).select_related(
                "plan__enrollment__student__user",
                "plan__enrollment__course",
                "plan__enrollment__batch",
                "recorded_by",
            ),
            pk=payment_id,
        )
        settings = effective_settings()
        support = " · ".join(
            part for part in (settings.support_email, settings.support_phone) if part
        )
        content = render_receipt_pdf(
            payment, institution_name=settings.institution_name, support_line=support
        )
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="receipt-{payment.receipt_number}.pdf"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
