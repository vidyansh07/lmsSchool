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

from django.db.models import Count, Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework import status as http_status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import has_capability
from apps.batches import access as batch_access
from apps.common.caching import MINUTE, remember
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.enrollments.models import Enrollment
from apps.organisation.models import Bank
from apps.students import access as students_access

from . import mail, services
from .models import FeeInstallment, FeePayment, FeePlan, PaymentCategory, TaxGroup
from .serializers import (
    BouncePaymentSerializer,
    CancelAdmissionSerializer,
    ClearPaymentSerializer,
    FeeCollectionsTrendPointSerializer,
    FeeCommentCreateSerializer,
    FeeCommentSerializer,
    FeeEmailQueuedSerializer,
    FeeEmailSerializer,
    FeeHistoryEntrySerializer,
    FeePaymentSerializer,
    FeePlanBriefSerializer,
    FeePlanSerializer,
    FeesOverviewSerializer,
    LedgerReconciliationSerializer,
    NamedListPatchSerializer,
    NamedListWriteSerializer,
    PaymentCategorySerializer,
    RecordPaymentSerializer,
    RefundPaymentSerializer,
    SetFeePlanSerializer,
    SetInstallmentsSerializer,
    SetNextDueSerializer,
    StudentFeeSummarySerializer,
    TaxGroupSerializer,
    VoidPaymentSerializer,
)

FEES_TAG = ["Fees"]


def _payment(user, payment_id) -> FeePayment:
    """One payment, out of the enrolments the caller may see — so a payment id
    from another centre is the same 404 a guessed id gets."""
    return get_object_or_404(
        FeePayment.objects.filter(
            plan__enrollment__in=batch_access.visible_enrollments(user)
        ).select_related("plan__enrollment__student", "plan__enrollment__batch"),
        pk=payment_id,
    )


def _reference_or_404(queryset, value):
    """One of the reference lists a payment points at (bank, category, tax
    group), or `None` when the field was left out. A named row that is not
    there — or has been retired — is a 404 about that row rather than a
    payment quietly recorded without it."""
    if not value:
        return None
    return get_object_or_404(queryset, pk=value)


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
        FeePlan.objects.select_related("enrollment__batch", "enrollment__course")
        .prefetch_related(
            "installments",
            # Counted here rather than per row: the serializer falls back to
            # counting one payment's own thread, which over a plan with
            # twenty payments would be twenty queries.
            Prefetch(
                "payments",
                queryset=FeePayment.objects.annotate(comment_count=Count("comments")),
            ),
        )
        .with_totals(),
        enrollment=enrollment,
    )


def _instalment(user, instalment_id) -> FeeInstallment:
    """One instalment, out of the enrolments the caller may see — the same
    narrowing `_payment` does, for the same reason."""
    return get_object_or_404(
        FeeInstallment.objects.filter(
            plan__enrollment__in=batch_access.visible_enrollments(user)
        ).select_related("plan__enrollment"),
        pk=instalment_id,
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


class EnrollmentFeeInstallmentsView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Replace the instalment schedule for an enrolment's fee",
        request=SetInstallmentsSerializer,
        responses={200: FeePlanSerializer},
        tags=FEES_TAG,
    )
    def put(self, request, enrollment_id):
        enrollment = _enrollment(request.user, enrollment_id)
        plan = _plan_or_404(enrollment)
        serializer = SetInstallmentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_installments(
            plan=plan, actor=request.user, items=serializer.validated_data["installments"]
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
        data = dict(serializer.validated_data)

        # Each of these is an id naming a row the payment points at. They are
        # resolved here rather than in the service so a bad id is a 404 about
        # that row, not a crash inside the ledger.
        bank = _reference_or_404(Bank.objects.active(), data.pop("bank", None))
        category = _reference_or_404(PaymentCategory.objects.active(), data.pop("category", None))
        tax_group = _reference_or_404(TaxGroup.objects.active(), data.pop("tax_group", None))
        instalment_id = data.pop("instalment", None)
        instalment = (
            get_object_or_404(plan.installments.all(), pk=instalment_id) if instalment_id else None
        )

        payment = services.record_payment(
            plan=plan,
            actor=request.user,
            bank=bank,
            category=category,
            tax_group=tax_group,
            instalment=instalment,
            **data,
        )
        return Response(FeePaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class FeePaymentClearView(APIView):
    """The bank honoured a cheque, a draft or a deposit."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY
    serializer_class = ClearPaymentSerializer

    @extend_schema(
        summary="Mark a payment cleared",
        request=ClearPaymentSerializer,
        responses={200: FeePaymentSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, payment_id):
        payment = _payment(request.user, payment_id)
        serializer = ClearPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cleared = services.mark_payment_cleared(
            payment=payment, actor=request.user, **serializer.validated_data
        )
        return Response(FeePaymentSerializer(cleared).data)


class FeePaymentBounceView(APIView):
    """It did not. The money is voided — the cheque was never payment — and
    the reason the bank gave is kept with it."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY
    serializer_class = BouncePaymentSerializer

    @extend_schema(
        summary="Mark a payment bounced",
        request=BouncePaymentSerializer,
        responses={200: FeePaymentSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, payment_id):
        payment = _payment(request.user, payment_id)
        serializer = BouncePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        bounced = services.mark_payment_bounced(
            payment=payment, actor=request.user, **serializer.validated_data
        )
        return Response(FeePaymentSerializer(bounced).data)


class CancelAdmissionView(APIView):
    """End an admission and settle its money in one request.

    One endpoint rather than "cancel the enrolment, then fix the fee",
    because they are one decision and doing half of it is how the two came to
    disagree.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Cancel an admission and settle its fee",
        request=CancelAdmissionSerializer,
        responses={200: FeePlanSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, enrollment_id):
        enrollment = get_object_or_404(
            batch_access.visible_enrollments(request.user), pk=enrollment_id
        )
        payload = CancelAdmissionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        plan = services.cancel_admission(
            enrollment=enrollment,
            actor=request.user,
            cancellation_charge=payload.validated_data["cancellation_charge"],
            reason=payload.validated_data["reason"],
        )
        return Response(FeePlanSerializer(plan).data)


class LedgerReconciliationView(APIView):
    """Does the money add up?

    Staff-only and scoped like every other figure here: computed over the
    enrolments the caller can already see, so a counsellor at one centre
    reconciles their own centre rather than the institute.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY

    @extend_schema(
        summary="Every rupee charged, placed in one bucket",
        responses={200: LedgerReconciliationSerializer},
        tags=FEES_TAG,
    )
    def get(self, request):
        return Response(
            LedgerReconciliationSerializer(services.ledger_reconciliation(user=request.user)).data
        )


class FeePaymentRefundView(APIView):
    """Give a payment back.

    Deliberately not a flag on the void endpoint. A void says the payment
    should never have been recorded; a refund says it was correct and the money
    has gone back. Separate routes keep them separate in the audit trail, where
    somebody will later need to tell them apart.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Refund a payment taken on refundable terms",
        request=RefundPaymentSerializer,
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
        serializer = RefundPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.refund_payment(
            payment=payment, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(FeePaymentSerializer(payment).data)


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
        student = batch_access.student_profile(request.user)
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


def _pdf_response(content: bytes, filename: str):
    from django.http import HttpResponse

    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


class EnrollmentFeeStatementView(APIView):
    """The fee statement as a PDF: the student's own, or staff who may read fees."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Download the fee statement for an enrolment",
        responses={200: OpenApiResponse(description="A PDF.")},
        tags=FEES_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment(request.user, enrollment_id)
        if not _may_read(request.user, enrollment):
            return Response(status=status.HTTP_403_FORBIDDEN)
        plan = _plan_or_404(enrollment)
        document = mail._render_statement(str(plan.pk))
        return _pdf_response(document.content, document.filename)


class EnrollmentFeeEmailsView(APIView):
    """Every fee mail about this enrolment — statements and receipts — newest first."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY

    @extend_schema(
        summary="Fee mails sent for an enrolment",
        responses={200: FeeEmailSerializer(many=True)},
        tags=FEES_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment(request.user, enrollment_id)
        plan = _plan_or_404(enrollment)
        receipt_numbers = {
            str(pk): number for pk, number in plan.payments.values_list("pk", "receipt_number")
        }
        rows = mail.emails_for_plan(plan)[:100]
        return Response(
            FeeEmailSerializer(rows, many=True, context={"receipt_numbers": receipt_numbers}).data
        )


class EnrollmentFeeEmailStatementView(APIView):
    """Send the fee statement to the student now."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Email the fee statement to the student",
        request=None,
        responses={202: FeeEmailQueuedSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, enrollment_id):
        from django.db import transaction

        enrollment = _enrollment(request.user, enrollment_id)
        plan = _plan_or_404(enrollment)
        with transaction.atomic():
            message = mail.email_statement(plan, automatic=False)
        return Response(FeeEmailQueuedSerializer(message).data, status=status.HTTP_202_ACCEPTED)


class FeePaymentEmailReceiptView(APIView):
    """Send a payment's receipt to the student again."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_MANAGE_ANY

    @extend_schema(
        summary="Email the receipt for a payment to the student",
        request=None,
        responses={202: FeeEmailQueuedSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, payment_id):
        from django.db import transaction

        payment = get_object_or_404(
            FeePayment.objects.filter(
                plan__enrollment__in=batch_access.visible_enrollments(request.user)
            ),
            pk=payment_id,
        )
        with transaction.atomic():
            message = mail.email_receipt(payment, automatic=False)
        return Response(FeeEmailQueuedSerializer(message).data, status=status.HTTP_202_ACCEPTED)


def _require_settings(user) -> None:
    """Reading these lists comes with reading fees; changing them does not."""
    if not has_capability(user, Capability.SETTINGS_MANAGE):
        raise PermissionDenied("You do not have permission to change the institution's lists.")


class PaymentCategoryListView(ListAPIView):
    """What a payment can be *for* — Fees, Registration, an exam fee.

    An administrator's list, read by the payment dialog. Gated on reading
    fees rather than managing them: the fee tab shows a payment's category on
    every row, so somebody who may read a payment may read the names.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY
    serializer_class = PaymentCategorySerializer
    pagination_class = None

    def get_queryset(self):
        # Whoever may manage the list sees the inactive rows too; a screen
        # that hides the row it is meant to reactivate is a screen with a
        # missing category.
        if has_capability(self.request.user, Capability.SETTINGS_MANAGE):
            return PaymentCategory.objects.all()
        return PaymentCategory.objects.active()

    @extend_schema(summary="Payment categories", tags=FEES_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Add a payment category",
        request=NamedListWriteSerializer,
        responses={201: PaymentCategorySerializer},
        tags=FEES_TAG,
    )
    def post(self, request, *args, **kwargs):
        from .settings_lists import create_payment_category

        _require_settings(request.user)
        payload = NamedListWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        category = create_payment_category(actor=request.user, **payload.validated_data)
        return Response(
            PaymentCategorySerializer(category).data, status=http_status.HTTP_201_CREATED
        )


class PaymentCategoryDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.SETTINGS_MANAGE
    serializer_class = PaymentCategorySerializer

    @extend_schema(
        summary="Change a payment category",
        request=NamedListPatchSerializer,
        responses={200: PaymentCategorySerializer},
        tags=FEES_TAG,
    )
    def patch(self, request, category_id):
        from .settings_lists import update_payment_category

        category = get_object_or_404(PaymentCategory.objects.all(), pk=category_id)
        payload = NamedListPatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        category = update_payment_category(
            actor=request.user, category=category, **payload.validated_data
        )
        return Response(PaymentCategorySerializer(category).data)


class TaxGroupListView(ListAPIView):
    """The named taxes a payment can be taken under. Recorded, never
    computed — see `apps.fees.models.TaxGroup`."""

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY
    serializer_class = TaxGroupSerializer
    pagination_class = None

    def get_queryset(self):
        if has_capability(self.request.user, Capability.SETTINGS_MANAGE):
            return TaxGroup.objects.all()
        return TaxGroup.objects.active()

    @extend_schema(summary="Tax groups", tags=FEES_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Add a tax group",
        request=NamedListWriteSerializer,
        responses={201: TaxGroupSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, *args, **kwargs):
        from .settings_lists import create_tax_group

        _require_settings(request.user)
        payload = NamedListWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        group = create_tax_group(actor=request.user, **payload.validated_data)
        return Response(TaxGroupSerializer(group).data, status=http_status.HTTP_201_CREATED)


class TaxGroupDetailView(APIView):
    permission_classes = (HasCapability,)
    required_capability = Capability.SETTINGS_MANAGE
    serializer_class = TaxGroupSerializer

    @extend_schema(
        summary="Change a tax group",
        request=NamedListPatchSerializer,
        responses={200: TaxGroupSerializer},
        tags=FEES_TAG,
    )
    def patch(self, request, group_id):
        from .settings_lists import update_tax_group

        group = get_object_or_404(TaxGroup.objects.all(), pk=group_id)
        payload = NamedListPatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        group = update_tax_group(actor=request.user, group=group, **payload.validated_data)
        return Response(TaxGroupSerializer(group).data)


class _CommentThreadView(APIView):
    """Read a thread, or add one message to it.

    Reading is `fee.view_any`, writing is `fee.manage_any`: a manager who may
    look at the money may read why a row is the way it is; only the people who
    record payments add to that record. The write capability is checked again
    in `services.add_comment`, so hiding the composer on the screen stays a
    courtesy and never the control.

    Nothing here is reachable by a student. Their own fee screen
    (`/fees/me/`) does not read comments, and these two endpoints need a
    staff capability, so a desk can write "says he will pay after the exam"
    without composing it for the student to read.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.FEE_VIEW_ANY
    serializer_class = FeeCommentSerializer

    def _thread(self, target):
        return target.comments.select_related("author").order_by("created_at")


class FeePaymentCommentsView(_CommentThreadView):
    @extend_schema(
        summary="A payment's comment thread",
        responses={200: FeeCommentSerializer(many=True)},
        tags=FEES_TAG,
    )
    def get(self, request, payment_id):
        payment = _payment(request.user, payment_id)
        return Response(FeeCommentSerializer(self._thread(payment), many=True).data)

    @extend_schema(
        summary="Comment on a payment",
        request=FeeCommentCreateSerializer,
        responses={201: FeeCommentSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, payment_id):
        payment = _payment(request.user, payment_id)
        serializer = FeeCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = services.add_comment(
            actor=request.user, payment=payment, body=serializer.validated_data["body"]
        )
        return Response(FeeCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class FeeInstallmentCommentsView(_CommentThreadView):
    @extend_schema(
        summary="An instalment's comment thread",
        responses={200: FeeCommentSerializer(many=True)},
        tags=FEES_TAG,
    )
    def get(self, request, instalment_id):
        instalment = _instalment(request.user, instalment_id)
        return Response(FeeCommentSerializer(self._thread(instalment), many=True).data)

    @extend_schema(
        summary="Comment on an instalment",
        request=FeeCommentCreateSerializer,
        responses={201: FeeCommentSerializer},
        tags=FEES_TAG,
    )
    def post(self, request, instalment_id):
        instalment = _instalment(request.user, instalment_id)
        serializer = FeeCommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = services.add_comment(
            actor=request.user, instalment=instalment, body=serializer.validated_data["body"]
        )
        return Response(FeeCommentSerializer(comment).data, status=status.HTTP_201_CREATED)
