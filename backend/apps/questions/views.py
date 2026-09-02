"""Question bank API.

Every endpoint here is staff-only, because every response carries the answers.
A student never reaches this router at all — ``visible_questions`` returns an
empty queryset for them, so even a capability misconfiguration one day would
produce an empty list rather than a leak.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import AuditAction, record
from apps.common.permissions import IsActiveUser
from apps.courses import access as course_access
from apps.courses.models import Module

from . import access, services
from .models import Question
from .serializers import QuestionSerializer, QuestionWriteSerializer

QUESTIONS_TAG = ["question bank"]


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


class QuestionFilterSet(django_filters.FilterSet):
    course = django_filters.UUIDFilter(field_name="course_id")
    question_type = django_filters.CharFilter(field_name="question_type", lookup_expr="exact")
    difficulty = django_filters.CharFilter(field_name="difficulty", lookup_expr="exact")
    is_active = django_filters.BooleanFilter(field_name="is_active")
    tag = django_filters.CharFilter(field_name="tags", lookup_expr="contains", method="filter_tag")

    class Meta:
        model = Question
        fields = ("course", "question_type", "difficulty", "is_active")

    def filter_tag(self, queryset, name, value):
        return queryset.filter(tags__contains=[value])


class QuestionListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = QuestionSerializer
    filter_backends = (DjangoFilterBackend, SearchFilter, OrderingFilter)
    filterset_class = QuestionFilterSet
    search_fields = ("text",)
    ordering_fields = ("created_at", "difficulty", "marks")
    ordering = ("-created_at",)

    def get_queryset(self):
        return access.visible_questions(self.request.user)

    @extend_schema(summary="List questions", tags=QUESTIONS_TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class QuestionCreateView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Create a question",
        request=QuestionWriteSerializer,
        responses={201: QuestionSerializer},
        tags=QUESTIONS_TAG,
    )
    def post(self, request):
        serializer = QuestionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)

        course = None
        course_id = fields.pop("course", None)
        if course_id:
            course = get_object_or_404(course_access.visible_courses(request.user), pk=course_id)

        if not access.can_write_questions_for(request.user, course):
            record(
                action=AuditAction.PERMISSION_DENIED,
                actor=request.user,
                resource_type="question",
                resource_id="",
                result="failure",
                context={"attempted": "question.create"},
            )
            return _forbidden(request, "You cannot write questions for that course.")

        module_id = fields.pop("module", None)
        if module_id:
            if course is None:
                return _forbidden(request, "A module-scoped question needs a course.")
            fields["module"] = get_object_or_404(Module.objects.filter(course=course), pk=module_id)

        options = fields.pop("options", None)
        question = services.create_question(
            actor=request.user, course=course, options=options, **fields
        )
        return Response(QuestionSerializer(question).data, status=http_status.HTTP_201_CREATED)


def _question_for(request, question_id, *, manage: bool = False) -> Question:
    source = (
        access.manageable_questions(request.user)
        if manage
        else access.visible_questions(request.user)
    )
    return get_object_or_404(source, pk=question_id)


class QuestionDetailView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Question detail", responses={200: QuestionSerializer}, tags=QUESTIONS_TAG
    )
    def get(self, request, question_id):
        return Response(QuestionSerializer(_question_for(request, question_id)).data)

    @extend_schema(
        summary="Edit a question",
        request=QuestionWriteSerializer,
        responses={200: QuestionSerializer},
        tags=QUESTIONS_TAG,
    )
    def patch(self, request, question_id):
        question = _question_for(request, question_id, manage=True)
        serializer = QuestionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        fields.pop("course", None)  # a question does not move between courses

        module_id = fields.pop("module", None)
        if module_id:
            fields["module"] = get_object_or_404(
                Module.objects.filter(course=question.course), pk=module_id
            )

        options = fields.pop("options", None)
        question = services.update_question(
            question=question, actor=request.user, options=options, **fields
        )
        return Response(QuestionSerializer(question).data)

    @extend_schema(
        summary="Delete a question",
        request=None,
        responses={204: OpenApiResponse(description="Deleted.")},
        tags=QUESTIONS_TAG,
    )
    def delete(self, request, question_id):
        question = _question_for(request, question_id, manage=True)
        services.delete_question(question=question, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)
