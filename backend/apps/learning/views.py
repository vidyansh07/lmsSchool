"""The student's learning surface — §7.5 and §7.7.

Everything here is scoped to the caller's own enrolments. There is no staff view
of a student's bookmarks or notes, because those are personal working material
rather than academic records — a trainer needs the progress report, not the
margin scribbles.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.courses.models import Lesson
from apps.enrollments.models import Enrollment

from . import services
from .models import LessonBookmark, LessonNote
from .serializers import (
    BookmarkSerializer,
    BookmarkWriteSerializer,
    HistoryEntrySerializer,
    LearningHomeSerializer,
    NoteSerializer,
    NoteWriteSerializer,
    PeerSerializer,
    UpcomingSerializer,
)

LEARNING_TAG = ["learning"]


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


def _my_enrollments(user):
    student = batch_access.student_profile(user)
    if student is None:
        return Enrollment.objects.none()
    return (
        Enrollment.objects.granting_access()
        .filter(student=student)
        .select_related("batch", "course")
    )


def _enrollment_for(request, enrollment_id) -> Enrollment:
    return get_object_or_404(_my_enrollments(request.user), pk=enrollment_id)


class LearningHomeView(APIView):
    """Continue learning, and what was open recently."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Where to pick up",
        responses={200: LearningHomeSerializer(many=True)},
        tags=LEARNING_TAG,
    )
    def get(self, request):
        payload = []
        for enrollment in _my_enrollments(request.user):
            if not enrollment.grants_access():
                continue
            payload.append(
                {
                    "enrollment_id": str(enrollment.pk),
                    "course_title": enrollment.course.title,
                    "course_slug": enrollment.course.slug,
                    "batch_code": enrollment.batch.code,
                    "continue_learning": services.continue_learning(enrollment),
                    "recent": services.recent_lessons(enrollment),
                }
            )
        return Response(LearningHomeSerializer(payload, many=True).data)


class UpcomingWorkView(APIView):
    """What is due soon, read from the one calendar."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My upcoming work",
        responses={200: UpcomingSerializer(many=True)},
        tags=LEARNING_TAG,
    )
    def get(self, request):
        return Response(UpcomingSerializer(services.upcoming_work(request.user), many=True).data)


class HistoryView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My learning history",
        responses={200: HistoryEntrySerializer(many=True)},
        tags=LEARNING_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)
        return Response(
            HistoryEntrySerializer(services.learning_history(enrollment), many=True).data
        )


class BookmarkListView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My bookmarks", responses={200: BookmarkSerializer(many=True)}, tags=LEARNING_TAG
    )
    def get(self, request):
        rows = LessonBookmark.objects.filter(
            enrollment__in=_my_enrollments(request.user)
        ).select_related("lesson", "lesson__module", "lesson__module__course")
        return Response(BookmarkSerializer(rows, many=True).data)


class NoteListView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My notes", responses={200: NoteSerializer(many=True)}, tags=LEARNING_TAG
    )
    def get(self, request):
        rows = LessonNote.objects.filter(
            enrollment__in=_my_enrollments(request.user)
        ).select_related("lesson", "lesson__module", "lesson__module__course")
        return Response(NoteSerializer(rows, many=True).data)


def _lesson_and_enrollment(request, lesson_id):
    """The lesson, and the caller's enrolment that opens it.

    A lesson id alone proves nothing: it is resolved against the enrolments the
    caller actually holds, so a lesson from another course 404s.
    """
    lesson = get_object_or_404(
        Lesson.objects.select_related("module", "module__course"), pk=lesson_id
    )
    enrollment = _my_enrollments(request.user).filter(course_id=lesson.module.course_id).first()
    if enrollment is None or not enrollment.grants_access():
        return lesson, None
    return lesson, enrollment


class LessonBookmarkView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Bookmark a lesson",
        request=BookmarkWriteSerializer,
        responses={200: BookmarkSerializer},
        tags=LEARNING_TAG,
    )
    def post(self, request, lesson_id):
        lesson, enrollment = _lesson_and_enrollment(request, lesson_id)
        if enrollment is None:
            return _forbidden(request, "You are not enrolled on this course.")

        serializer = BookmarkWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        bookmark = services.set_bookmark(
            enrollment=enrollment, lesson=lesson, note=serializer.validated_data.get("note", "")
        )
        return Response(BookmarkSerializer(bookmark).data)

    @extend_schema(
        summary="Remove a bookmark",
        request=None,
        responses={204: OpenApiResponse(description="Removed.")},
        tags=LEARNING_TAG,
    )
    def delete(self, request, lesson_id):
        lesson, enrollment = _lesson_and_enrollment(request, lesson_id)
        if enrollment is None:
            return _forbidden(request, "You are not enrolled on this course.")
        services.remove_bookmark(enrollment=enrollment, lesson=lesson)
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class LessonNoteView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My note on a lesson",
        responses={200: NoteSerializer},
        tags=LEARNING_TAG,
    )
    def get(self, request, lesson_id):
        lesson, enrollment = _lesson_and_enrollment(request, lesson_id)
        if enrollment is None:
            return _forbidden(request, "You are not enrolled on this course.")
        note = LessonNote.objects.filter(enrollment=enrollment, lesson=lesson).first()
        return Response(NoteSerializer(note).data if note else {})

    @extend_schema(
        summary="Write a note on a lesson",
        request=NoteWriteSerializer,
        responses={200: NoteSerializer},
        tags=LEARNING_TAG,
    )
    def put(self, request, lesson_id):
        lesson, enrollment = _lesson_and_enrollment(request, lesson_id)
        if enrollment is None:
            return _forbidden(request, "You are not enrolled on this course.")

        serializer = NoteWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = services.set_note(
            enrollment=enrollment, lesson=lesson, body=serializer.validated_data["body"]
        )
        return Response(NoteSerializer(note).data if note else {})


class BatchDirectoryView(APIView):
    """Who else is on my batch — §7.7.

    Names and student codes only. No email, no phone, no profile: §7.7 says not
    to expose contact data by default, and "by default" here means "at all",
    because there is no mechanism in this product for a student to opt in to
    being contactable and no reason to invent one.

    Gated by the academic configuration, so an institution that does not want a
    class list can switch it off.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Who else is on my batch",
        responses={200: PeerSerializer(many=True)},
        tags=LEARNING_TAG,
    )
    def get(self, request, enrollment_id):
        enrollment = _enrollment_for(request, enrollment_id)

        from apps.academics.policies import policy_for

        if not policy_for(enrollment.course_id).batch_directory_visible:
            return _forbidden(request, "The class list is not shared on this course.")

        from apps.enrollments.models import EnrollmentStatus

        peers = (
            Enrollment.objects.filter(
                batch_id=enrollment.batch_id,
                status__in=(EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED),
            )
            .select_related("student", "student__user")
            .order_by("student__student_id")
        )
        payload = [
            {
                "full_name": row.student.user.get_full_name(),
                "student_code": row.student.student_id,
                "is_you": row.pk == enrollment.pk,
            }
            for row in peers
        ]
        return Response(PeerSerializer(payload, many=True).data)
