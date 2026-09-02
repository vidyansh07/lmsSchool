"""Examination API.

Every candidate-facing response is built from the *frozen* paper on the
attempt, never from the question bank, and every one of them recomputes the
remaining time on the server. A client cannot ask for a question it was not
given, cannot see an answer key, and cannot influence its own clock.
"""

from __future__ import annotations

import django_filters
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditAction, record
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser

from . import access, services
from .models import AttemptAnswer, AttemptQuestion, AttemptStatus, Exam, ExamAttempt
from .serializers import (
    AttemptPaperSerializer,
    AttemptResultSerializer,
    AttemptReviewSerializer,
    AttemptSerializer,
    ExamSerializer,
    ExamStatusSerializer,
    ExamWriteSerializer,
    MarkableAnswerSerializer,
    MarkAnswerSerializer,
    PublishResultsSerializer,
    ReadinessSerializer,
    SaveAnswerSerializer,
    StaffAttemptSerializer,
    candidate_question_payload,
)

EXAMS_TAG = ["examinations"]


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


class ExamFilterSet(django_filters.FilterSet):
    batch = django_filters.UUIDFilter(field_name="batch_id")
    course = django_filters.UUIDFilter(field_name="course_id")
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")

    class Meta:
        model = Exam
        fields = ("batch", "course", "status")


class ExamListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = ExamSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = ExamFilterSet
    search_fields = ("title", "code")
    ordering_fields = ("opens_at", "created_at", "title")
    ordering = ("-opens_at",)

    def get_queryset(self):
        return access.visible_exams(self.request.user)

    @extend_schema(summary="List examinations", tags=EXAMS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BatchExamsView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Create an examination",
        request=ExamWriteSerializer,
        responses={201: ExamSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, batch_id):
        batch = get_object_or_404(batch_access.visible_batches(request.user), pk=batch_id)
        if not access.can_set_exams_on(request.user, batch):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="batch",
                resource_id=batch.pk,
                result="failure",
                context={"attempted": "exam.create"},
            )
            return _forbidden(request, "You cannot set examinations on this batch.")

        serializer = ExamWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        sections = fields.pop("sections", None)

        exam = services.create_exam(actor=request.user, batch=batch, sections=sections, **fields)
        return Response(ExamSerializer(exam).data, status=http_status.HTTP_201_CREATED)


def _exam_for(request, exam_id, *, manage: bool = False) -> Exam:
    source = access.manageable_exams(request.user) if manage else access.visible_exams(request.user)
    return get_object_or_404(source, pk=exam_id)


class ExamDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(summary="Examination detail", responses={200: ExamSerializer}, tags=EXAMS_TAG)
    def get(self, request, exam_id):
        return Response(ExamSerializer(_exam_for(request, exam_id)).data)

    @extend_schema(
        summary="Edit an examination",
        request=ExamWriteSerializer,
        responses={200: ExamSerializer},
        tags=EXAMS_TAG,
    )
    def patch(self, request, exam_id):
        exam = _exam_for(request, exam_id, manage=True)
        serializer = ExamWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        sections = fields.pop("sections", None)
        exam = services.update_exam(exam=exam, actor=request.user, sections=sections, **fields)
        return Response(ExamSerializer(exam).data)


class ExamStatusView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish, close or archive an examination",
        request=ExamStatusSerializer,
        responses={200: ExamSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, exam_id):
        exam = _exam_for(request, exam_id, manage=True)
        serializer = ExamStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exam = services.set_exam_status(
            exam=exam, actor=request.user, status=serializer.validated_data["status"]
        )
        return Response(ExamSerializer(exam).data)


class ExamReadinessView(APIView):
    """Can this paper actually be drawn? Asked before publishing."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Examination readiness", responses={200: ReadinessSerializer}, tags=EXAMS_TAG
    )
    def get(self, request, exam_id):
        exam = _exam_for(request, exam_id, manage=True)
        return Response(ReadinessSerializer(services.check_readiness(exam)).data)


class ExamResultsPublishView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Publish or withhold results",
        request=PublishResultsSerializer,
        responses={200: ExamSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, exam_id):
        exam = _exam_for(request, exam_id, manage=True)
        if not access.can_grade(request.user, exam):
            return _forbidden(request, "You cannot publish results for this examination.")
        serializer = PublishResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        exam = services.publish_results(
            exam=exam, actor=request.user, published=serializer.validated_data["published"]
        )
        return Response(ExamSerializer(exam).data)


class MyExamsView(ListAPIView):
    """A candidate's examinations."""

    permission_classes = (IsActiveUser,)
    serializer_class = ExamSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = ExamFilterSet
    ordering_fields = ("opens_at",)
    ordering = ("-opens_at",)

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return Exam.objects.none()
        return access.visible_exams(self.request.user)

    @extend_schema(summary="My examinations", tags=EXAMS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Sitting
# ---------------------------------------------------------------------------


def _paper_response(attempt: ExamAttempt) -> Response:
    rows = (
        attempt.questions.select_related("question", "section")
        .prefetch_related("question__options", "answer")
        .order_by("position")
    )
    return Response(
        AttemptPaperSerializer(
            {
                "attempt": attempt,
                "questions": [candidate_question_payload(row) for row in rows],
            }
        ).data
    )


class StartAttemptView(APIView):
    """Start, or resume, my attempt.

    The same call every time: pressing Start twice, refreshing, or coming back
    on another device all return the attempt that already exists, with the same
    paper and the same clock.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Start or resume an examination attempt",
        request=None,
        responses={200: AttemptPaperSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, exam_id):
        exam = _exam_for(request, exam_id)
        student = batch_access.student_profile(request.user)
        if student is None:
            return _forbidden(request, "Only enrolled students sit examinations.")

        enrollment = services.enrollment_for(exam=exam, student=student)
        if enrollment is None:
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="exam",
                resource_id=exam.pk,
                result="failure",
                context={"attempted": "exam.start"},
            )
            return _forbidden(request, "You are not on the batch this examination is set for.")

        attempt = services.start_attempt(exam=exam, enrollment=enrollment, actor=request.user)
        return _paper_response(attempt)


def _own_attempt(request, attempt_id) -> ExamAttempt:
    attempt = get_object_or_404(access.visible_attempts(request.user), pk=attempt_id)
    student = batch_access.student_profile(request.user)
    if student is None or attempt.enrollment.student_id != student.pk:
        # Staff may read an attempt, but only the candidate may answer it.
        raise Http404
    return attempt


class AttemptPaperView(APIView):
    """Resume: the paper, the saved answers and the remaining time."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My attempt and its paper",
        responses={200: AttemptPaperSerializer},
        tags=EXAMS_TAG,
    )
    def get(self, request, attempt_id):
        attempt = _own_attempt(request, attempt_id)
        attempt = services.refresh_if_expired(attempt, actor=request.user)
        return _paper_response(attempt)


class SaveAnswerView(APIView):
    """Auto-save one answer."""

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @extend_schema(
        summary="Save an answer",
        request=SaveAnswerSerializer,
        responses={200: AttemptSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, attempt_id, question_id):
        attempt = _own_attempt(request, attempt_id)
        attempt_question = get_object_or_404(
            AttemptQuestion.objects.filter(attempt=attempt).select_related("question"),
            pk=question_id,
        )

        serializer = SaveAnswerSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        services.save_answer(
            attempt=attempt,
            attempt_question=attempt_question,
            actor=request.user,
            selected_options=data.get("selected_options"),
            text_answer=data.get("text_answer"),
            uploaded_file=data.get("file"),
        )
        attempt.refresh_from_db()
        return Response(AttemptSerializer(attempt).data)


class SubmitAttemptView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Submit my attempt",
        request=None,
        responses={200: AttemptResultSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, attempt_id):
        attempt = _own_attempt(request, attempt_id)
        if attempt.has_expired:
            attempt = services.finalise_expired(attempt=attempt, actor=request.user)
            return Response(AttemptResultSerializer(attempt).data)
        attempt = services.submit_attempt(attempt=attempt, actor=request.user)
        return Response(AttemptResultSerializer(attempt).data)


class MyAttemptsView(ListAPIView):
    """My attempts and their results, when they have been published."""

    permission_classes = (IsActiveUser,)
    serializer_class = AttemptResultSerializer
    filter_backends = (OrderingFilter,)
    ordering_fields = ("submitted_at", "started_at")
    ordering = ("-started_at",)

    def get_queryset(self):
        student = batch_access.student_profile(self.request.user)
        if student is None:
            return ExamAttempt.objects.none()
        return access.visible_attempts(self.request.user)

    @extend_schema(summary="My examination attempts", tags=EXAMS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class AttemptResultView(APIView):
    """One attempt's result.

    Scores are blanked until the exam publishes them — the fields are present so
    the shape is stable, but they carry nothing a candidate is not entitled to
    yet.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="An attempt's result", responses={200: AttemptResultSerializer}, tags=EXAMS_TAG
    )
    def get(self, request, attempt_id):
        attempt = get_object_or_404(access.visible_attempts(request.user), pk=attempt_id)
        attempt = services.refresh_if_expired(attempt, actor=request.user)

        if access.can_grade(request.user, attempt.exam):
            return Response(StaffAttemptSerializer(attempt).data)

        payload = AttemptResultSerializer(attempt).data
        if not attempt.exam.results_published:
            for field in ("total_score", "max_score", "is_passing", "percentage", "graded_at"):
                payload[field] = None
        return Response(payload)


class AttemptReviewView(APIView):
    """A candidate's paper with the outcome, once results are published."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Review a marked attempt",
        responses={200: AttemptReviewSerializer},
        tags=EXAMS_TAG,
    )
    def get(self, request, attempt_id):
        attempt = get_object_or_404(access.visible_attempts(request.user), pk=attempt_id)
        is_staff = access.can_grade(request.user, attempt.exam)
        if not is_staff and not attempt.exam.results_published:
            return _forbidden(request, "Results for this examination have not been released.")

        rows = (
            attempt.questions.select_related("question")
            .prefetch_related("answer")
            .order_by("position")
        )
        questions = []
        for row in rows:
            answer = getattr(row, "answer", None)
            questions.append(
                {
                    "position": row.position,
                    "question_text": row.question.text,
                    "question_type": row.question.question_type,
                    "marks": row.marks,
                    "awarded": answer.awarded if answer else None,
                    "is_correct": answer.is_correct if answer else None,
                    "explanation": row.question.explanation,
                    "marker_feedback": answer.marker_feedback if answer else "",
                }
            )
        return Response(AttemptReviewSerializer({"attempt": attempt, "questions": questions}).data)


# ---------------------------------------------------------------------------
# Marking
# ---------------------------------------------------------------------------


class ExamAttemptsView(ListAPIView):
    """Every sitting of one examination — the marking queue."""

    permission_classes = (IsActiveUser,)
    serializer_class = StaffAttemptSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    ordering_fields = ("submitted_at", "total_score")
    ordering = ("-submitted_at",)
    queryset = ExamAttempt.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ExamAttempt.objects.none()
        exam = _exam_for(self.request, self.kwargs["exam_id"], manage=True)
        return access.visible_attempts(self.request.user).filter(exam=exam)

    @extend_schema(summary="Attempts on an examination", tags=EXAMS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class MarkingQueueView(APIView):
    """The written answers on one examination that still need a person."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Answers awaiting marking",
        responses={200: MarkableAnswerSerializer(many=True)},
        tags=EXAMS_TAG,
    )
    def get(self, request, exam_id):
        exam = _exam_for(request, exam_id, manage=True)
        if not access.can_grade(request.user, exam):
            return _forbidden(request, "You cannot mark this examination.")

        rows = (
            AttemptAnswer.objects.filter(
                attempt_question__attempt__exam=exam, needs_manual_marking=True
            )
            .select_related(
                "attempt_question",
                "attempt_question__question",
                "attempt_question__attempt",
                "attempt_question__attempt__enrollment__student__user",
            )
            .order_by("attempt_question__attempt_id", "attempt_question__position")
        )

        payload = []
        for answer in rows:
            attempt_question = answer.attempt_question
            student = attempt_question.attempt.enrollment.student
            payload.append(
                {
                    "id": answer.pk,
                    "attempt": attempt_question.attempt_id,
                    "position": attempt_question.position,
                    "question_text": attempt_question.question.text,
                    "question_type": attempt_question.question.question_type,
                    "marks": attempt_question.marks,
                    "text_answer": answer.text_answer,
                    "answered_filename": answer.original_filename,
                    "awarded": answer.awarded,
                    "marker_feedback": answer.marker_feedback,
                    "student_id": student.student_id,
                    "student_name": student.user.get_full_name(),
                }
            )
        return Response(MarkableAnswerSerializer(payload, many=True).data)


class MarkAnswerView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Mark one written answer",
        request=MarkAnswerSerializer,
        responses={200: StaffAttemptSerializer},
        tags=EXAMS_TAG,
    )
    def post(self, request, answer_id):
        answer = get_object_or_404(
            AttemptAnswer.objects.filter(
                attempt_question__attempt__in=access.visible_attempts(request.user)
            ).select_related("attempt_question__attempt__exam"),
            pk=answer_id,
        )
        exam = answer.attempt_question.attempt.exam
        if not access.can_grade(request.user, exam):
            raise Http404

        serializer = MarkAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.mark_written_answer(
            answer=answer,
            actor=request.user,
            awarded=serializer.validated_data["awarded"],
            feedback=serializer.validated_data.get("feedback", ""),
        )
        attempt = answer.attempt_question.attempt
        attempt.refresh_from_db()
        return Response(StaffAttemptSerializer(attempt).data)


# Referenced by the admin so the vocabulary has one home.
ATTEMPT_STATUSES = AttemptStatus
