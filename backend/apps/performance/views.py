"""Performance, review and feedback API."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.batches import access as batch_access
from apps.common.deletion import soft_delete
from apps.common.exceptions import ApplicationError
from apps.common.permissions import HasCapability, IsActiveUser

from . import access, engine, services
from .models import Feedback, PerformanceReview
from .serializers import (
    DeleteReasonSerializer,
    FeedbackSerializer,
    FeedbackWriteSerializer,
    PerformanceReviewSerializer,
    ReviewUpdateSerializer,
    ReviewWriteSerializer,
    RiskThresholdsSerializer,
)

PERFORMANCE_TAG = ["performance"]


def _forbidden(request, message: str) -> Response:
    return Response(
        {
            "error": {
                "code": "permission_denied",
                "message": message,
                "request_id": getattr(request, "request_id", "-"),
            }
        },
        status=http_status.HTTP_403_FORBIDDEN,
    )


def _resolve_subject(data: dict) -> tuple:
    """Turn the ``student``/``trainer`` ids a write submits into profiles."""
    from apps.students.models import StudentProfile
    from apps.trainers.models import TrainerProfile

    student_id = data.get("student")
    trainer_id = data.get("trainer")
    student = get_object_or_404(StudentProfile, pk=student_id) if student_id else None
    trainer = get_object_or_404(TrainerProfile, pk=trainer_id) if trainer_id else None
    return student, trainer


class MyPerformanceView(APIView):
    """A student's own performance, per enrolment. Empty for anyone else."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My performance",
        responses={200: OpenApiResponse(description="One entry per enrolment.")},
        tags=PERFORMANCE_TAG,
    )
    def get(self, request):
        from apps.enrollments.models import Enrollment

        student = batch_access.student_profile(request.user)
        if student is None:
            return Response([])

        rows = list(
            Enrollment.objects.with_related().filter(student=student).order_by("-enrolled_at")
        )
        performance = engine.student_performance_bulk(rows)
        return Response([performance[row.pk] for row in rows])


class MyTrainerPerformanceView(APIView):
    """A trainer's own performance figures.

    A caller with no trainer profile gets 404, not an empty object. That matches
    `/api/v1/trainers/me/`, which is the same question asked of the same person,
    and the distinction matters: `{}` says "you are a trainer with nothing
    recorded", which is a different and misleading answer to give a student.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My trainer performance",
        responses={
            200: OpenApiResponse(description="This trainer's own figures."),
            404: OpenApiResponse(description="The caller is not a trainer."),
        },
        tags=PERFORMANCE_TAG,
    )
    def get(self, request):
        trainer = batch_access.trainer_profile(request.user)
        if trainer is None:
            raise Http404
        return Response(engine.trainer_performance(trainer))


class BatchPerformanceView(APIView):
    """A batch's roster, from its trainer's point of view (or staff's)."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Batch performance",
        responses={200: OpenApiResponse(description="One entry per enrolment on this batch.")},
        tags=PERFORMANCE_TAG,
    )
    def get(self, request, batch_id):
        from apps.enrollments.models import Enrollment

        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not access.can_view_batch_performance(request.user, batch):
            return _forbidden(request, "You cannot view this batch's performance.")

        rows = list(Enrollment.objects.with_related().filter(batch=batch).order_by("-enrolled_at"))
        performance = engine.student_performance_bulk(rows)
        return Response([performance[row.pk] for row in rows])


class ReviewListView(APIView):
    """The review register: everyone's, or only one's own."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Performance reviews",
        responses={200: PerformanceReviewSerializer(many=True)},
        tags=PERFORMANCE_TAG,
    )
    def get(self, request):
        reviews = access.visible_reviews(request.user).order_by("-period_end", "-created_at")
        return Response(PerformanceReviewSerializer(reviews, many=True).data)

    @extend_schema(
        summary="Write a performance review",
        request=ReviewWriteSerializer,
        responses={201: PerformanceReviewSerializer},
        tags=PERFORMANCE_TAG,
    )
    def post(self, request):
        if not access.can_manage_reviews(request.user):
            return _forbidden(request, "You cannot record a performance review.")

        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        student, trainer = _resolve_subject(data)
        data.pop("student", None)
        data.pop("trainer", None)

        review = services.create_review(
            actor=request.user, student=student, trainer=trainer, **data
        )
        return Response(
            PerformanceReviewSerializer(review).data, status=http_status.HTTP_201_CREATED
        )


class ReviewDetailView(APIView):
    permission_classes = (IsActiveUser,)

    def _review_for(self, request, review_id) -> PerformanceReview:
        return get_object_or_404(access.visible_reviews(request.user), pk=review_id)

    @extend_schema(
        summary="A performance review",
        responses={200: PerformanceReviewSerializer},
        tags=PERFORMANCE_TAG,
    )
    def get(self, request, review_id):
        review = self._review_for(request, review_id)
        return Response(PerformanceReviewSerializer(review).data)

    @extend_schema(
        summary="Edit a performance review",
        request=ReviewUpdateSerializer,
        responses={200: PerformanceReviewSerializer},
        tags=PERFORMANCE_TAG,
    )
    def patch(self, request, review_id):
        review = self._review_for(request, review_id)
        if not access.can_manage_reviews(request.user):
            return _forbidden(request, "You cannot edit performance reviews.")

        serializer = ReviewUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        review = services.update_review(
            review=review, actor=request.user, **serializer.validated_data
        )
        return Response(PerformanceReviewSerializer(review).data)

    @extend_schema(
        summary="Withdraw a performance review",
        request=DeleteReasonSerializer,
        responses={204: None},
        tags=PERFORMANCE_TAG,
    )
    def delete(self, request, review_id):
        review = self._review_for(request, review_id)
        if not access.can_manage_reviews(request.user):
            return _forbidden(request, "You cannot withdraw performance reviews.")

        serializer = DeleteReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        soft_delete(instance=review, actor=request.user, reason=serializer.validated_data["reason"])
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class FeedbackListView(APIView):
    """Feedback: everyone's, one's own, or whatever was marked visible to them.

    `student` and `trainer` narrow the list to one subject. They are a
    convenience over an already-scoped queryset, never a way to widen it: the
    filter is applied *after* `visible_feedback`, so naming somebody else's id
    returns nothing rather than their feedback.

    Added because the screens were fetching the whole visible set and matching
    client-side, which works until somebody has a thousand rows and is the sort
    of thing that quietly becomes a performance bug on a page nobody profiled.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Feedback",
        parameters=[
            OpenApiParameter("student", str, description="Only feedback about this student."),
            OpenApiParameter("trainer", str, description="Only feedback about this trainer."),
        ],
        responses={200: FeedbackSerializer(many=True)},
        tags=PERFORMANCE_TAG,
    )
    def get(self, request):
        rows = access.visible_feedback(request.user).order_by("-created_at")

        student_id = request.query_params.get("student")
        trainer_id = request.query_params.get("trainer")
        try:
            if student_id:
                rows = rows.filter(student_id=student_id)
            if trainer_id:
                rows = rows.filter(trainer_id=trainer_id)
        except (ValueError, ValidationError):
            # A malformed uuid is a bad request, not a 500 and not silently the
            # unfiltered list — which would hand back more than was asked for.
            raise ApplicationError({"detail": ["Not a valid identifier."]}) from None

        return Response(FeedbackSerializer(rows, many=True).data)

    @extend_schema(
        summary="Leave feedback",
        request=FeedbackWriteSerializer,
        responses={201: FeedbackSerializer},
        tags=PERFORMANCE_TAG,
    )
    def post(self, request):
        if not access.can_manage_reviews(request.user):
            return _forbidden(request, "You cannot record feedback.")

        serializer = FeedbackWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        student, trainer = _resolve_subject(data)

        batch = None
        batch_id = data.get("batch")
        if batch_id:
            from apps.batches.models import Batch

            batch = get_object_or_404(Batch.objects.all(), pk=batch_id)

        feedback = services.create_feedback(
            actor=request.user,
            student=student,
            trainer=trainer,
            batch=batch,
            body=data["body"],
            visible_to_subject=data.get("visible_to_subject", True),
        )
        return Response(FeedbackSerializer(feedback).data, status=http_status.HTTP_201_CREATED)


class FeedbackDetailView(APIView):
    permission_classes = (IsActiveUser,)

    def _feedback_for(self, request, feedback_id) -> Feedback:
        return get_object_or_404(access.visible_feedback(request.user), pk=feedback_id)

    @extend_schema(
        summary="Withdraw feedback",
        request=DeleteReasonSerializer,
        responses={204: None},
        tags=PERFORMANCE_TAG,
    )
    def delete(self, request, feedback_id):
        feedback = self._feedback_for(request, feedback_id)
        if not access.can_manage_reviews(request.user):
            return _forbidden(request, "You cannot withdraw feedback.")

        serializer = DeleteReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        soft_delete(
            instance=feedback, actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class RiskThresholdsView(APIView):
    """The institution-wide numbers `apps.performance.risk` reads.

    Configuration, not a record about a person, so it takes the same
    capability as the rest of the academic rule book — `academic.configure` —
    rather than `review.manage_any`.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.ACADEMIC_CONFIGURE

    @extend_schema(
        summary="Current risk thresholds",
        responses={200: OpenApiResponse(description="The effective, institution-wide thresholds.")},
        tags=PERFORMANCE_TAG,
    )
    def get(self, request):
        from apps.academics.policies import policy_for

        policy = policy_for(None)
        return Response(
            {
                "risk_attendance_percent": str(policy.risk_attendance_percent),
                "risk_assessment_average_percent": str(policy.risk_assessment_average_percent),
                "risk_missed_assignments": policy.risk_missed_assignments,
                "risk_progress_variance_percent": str(policy.risk_progress_variance_percent),
            }
        )

    @extend_schema(
        summary="Change the risk thresholds",
        request=RiskThresholdsSerializer,
        responses={200: OpenApiResponse(description="The updated thresholds.")},
        tags=PERFORMANCE_TAG,
    )
    def patch(self, request):
        serializer = RiskThresholdsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = services.update_risk_thresholds(actor=request.user, **serializer.validated_data)
        return Response(
            {
                "risk_attendance_percent": str(policy.risk_attendance_percent),
                "risk_assessment_average_percent": str(policy.risk_assessment_average_percent),
                "risk_missed_assignments": policy.risk_missed_assignments,
                "risk_progress_variance_percent": str(policy.risk_progress_variance_percent),
            }
        )


__all__ = [
    "BatchPerformanceView",
    "FeedbackDetailView",
    "FeedbackListView",
    "MyPerformanceView",
    "MyTrainerPerformanceView",
    "ReviewDetailView",
    "ReviewListView",
    "RiskThresholdsView",
]
