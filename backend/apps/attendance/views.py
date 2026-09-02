"""Attendance API.

Two audiences with different needs:

* a **trainer** finishing a class wants the register for that class, prefilled,
  and one request to save it;
* a **student** wants their own history and percentage.

Both resolve their records through the session and enrolment access layers, so
there is no third copy of "whose batch is this?".
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.policies import attendance_requirement
from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.common.permissions import IsActiveUser
from apps.enrollments.models import Enrollment
from apps.sessions import access as session_access

from . import services
from .models import AttendanceRecord
from .serializers import (
    AdminAttendanceRecordSerializer,
    AttendanceRecordSerializer,
    AttendanceSummarySerializer,
    CorrectAttendanceSerializer,
    MarkAttendanceSerializer,
    MarkResultSerializer,
    RegisterSerializer,
)

ATTENDANCE_TAG = ["attendance"]


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


class SessionRegisterView(APIView):
    """The register for one class: read it, then save it.

    The GET returns every student who should be there together with their
    current mark, so the trainer's screen is one request. The POST takes the
    whole register back in one transaction.
    """

    permission_classes = (IsActiveUser,)

    def _session(self, request, session_id):
        return get_object_or_404(session_access.visible_sessions(request.user), pk=session_id)

    @extend_schema(
        summary="Get a class register", responses={200: RegisterSerializer}, tags=ATTENDANCE_TAG
    )
    def get(self, request, session_id):
        session = self._session(request, session_id)
        if not session_access.can_take_attendance(request.user, session):
            return _forbidden(request, "You do not take attendance for this class.")

        marks = {
            str(row.enrollment_id): row for row in AttendanceRecord.objects.filter(session=session)
        }
        entries = []
        for enrollment in services.roster_for(session):
            mark = marks.get(str(enrollment.pk))
            entries.append(
                {
                    "enrollment_id": enrollment.pk,
                    "student_code": enrollment.student.student_id,
                    "full_name": enrollment.student.user.full_name,
                    "enrollment_status": enrollment.status,
                    "status": mark.status if mark else None,
                    "note": mark.note if mark else "",
                    "was_corrected": mark.was_corrected if mark else False,
                }
            )

        return Response(
            {
                "session_id": session.pk,
                "session_date": session.session_date,
                "batch_code": session.batch.code,
                "can_mark": session.can_take_attendance,
                "attendance_taken_at": session.attendance_taken_at,
                "entries": entries,
            }
        )

    @extend_schema(
        summary="Save a class register",
        request=MarkAttendanceSerializer,
        responses={
            200: MarkResultSerializer,
            400: OpenApiResponse(description="Invalid register."),
            403: OpenApiResponse(description="Not your class."),
        },
        tags=ATTENDANCE_TAG,
    )
    def post(self, request, session_id):
        session = self._session(request, session_id)
        if not session_access.can_take_attendance(request.user, session):
            return _forbidden(request, "You do not take attendance for this class.")

        serializer = MarkAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.mark_attendance(
            session=session, actor=request.user, entries=serializer.validated_data["entries"]
        )
        return Response(result)


class SessionAttendanceListView(APIView):
    """Everyone's marks for one class. Staff view."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Attendance for a class",
        responses={200: AdminAttendanceRecordSerializer},
        tags=ATTENDANCE_TAG,
    )
    def get(self, request, session_id):
        session = get_object_or_404(session_access.visible_sessions(request.user), pk=session_id)
        if not (
            has_capability(request.user, Capability.ATTENDANCE_VIEW_ANY)
            or session_access.can_take_attendance(request.user, session)
        ):
            return _forbidden(request, "You do not have permission to see this register.")

        rows = (
            AttendanceRecord.objects.with_related()
            .filter(session=session)
            .order_by("enrollment__student__student_id")
        )
        return Response(AdminAttendanceRecordSerializer(rows, many=True).data)


class AttendanceCorrectionView(APIView):
    """Change one mark, with a reason. Audited separately from bulk marking."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Correct one attendance mark",
        request=CorrectAttendanceSerializer,
        responses={200: AdminAttendanceRecordSerializer},
        tags=ATTENDANCE_TAG,
    )
    def post(self, request, record_id):
        row = get_object_or_404(
            AttendanceRecord.objects.with_related().filter(
                session__in=session_access.visible_sessions(request.user)
            ),
            pk=record_id,
        )
        if not session_access.can_take_attendance(request.user, row.session):
            return _forbidden(request, "You do not have permission to change this record.")

        serializer = CorrectAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = services.correct_record(
            record_row=row,
            actor=request.user,
            status=serializer.validated_data["status"],
            reason=serializer.validated_data["reason"],
        )
        return Response(AdminAttendanceRecordSerializer(updated).data)


class MyAttendanceView(APIView):
    """A student's own attendance across all their enrolments."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="My attendance", responses={200: AttendanceSummarySerializer}, tags=ATTENDANCE_TAG
    )
    def get(self, request):
        student = batch_access.student_profile(request.user)
        if student is None:
            return Response([])

        payload = []
        enrollments = (
            Enrollment.objects.with_related().filter(student=student).order_by("-enrolled_at")
        )
        for enrollment in enrollments:
            rows = (
                AttendanceRecord.objects.filter(enrollment=enrollment)
                .select_related("session", "session__batch")
                .order_by("-session__session_date")
            )
            payload.append(
                {
                    "enrollment_id": str(enrollment.pk),
                    "course_title": enrollment.course.title,
                    "batch_code": enrollment.batch.code,
                    "summary": AttendanceSummarySerializer(attendance_requirement(enrollment)).data,
                    "records": AttendanceRecordSerializer(rows, many=True).data,
                }
            )
        return Response(payload)


class EnrollmentAttendanceView(APIView):
    """Attendance for one enrolment. The owner, their trainer, or staff."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Attendance on an enrolment",
        responses={200: AttendanceSummarySerializer},
        tags=ATTENDANCE_TAG,
    )
    def get(self, request, enrollment_id):
        # Resolved inside the caller's own visible enrolments, so another
        # student's id is simply not found.
        enrollment = get_object_or_404(
            batch_access.visible_enrollments(request.user), pk=enrollment_id
        )
        rows = (
            AttendanceRecord.objects.filter(enrollment=enrollment)
            .select_related("session", "session__batch")
            .order_by("-session__session_date")
        )
        is_staff = has_capability(request.user, Capability.ATTENDANCE_VIEW_ANY)
        serializer = AdminAttendanceRecordSerializer if is_staff else AttendanceRecordSerializer
        return Response(
            {
                "summary": AttendanceSummarySerializer(attendance_requirement(enrollment)).data,
                "records": serializer(rows, many=True).data,
            }
        )
