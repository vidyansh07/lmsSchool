"""Academic configuration API — §4.7.

Reading the rules is open to any signed-in user: a student is entitled to know
what attendance they need and what counts as a pass. Changing them needs
``ACADEMIC_CONFIGURE``, which sits on the administrator rung of the ladder,
because a pass mark moved retrospectively is a decision about people's records.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status as http_status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.common.permissions import IsActiveUser, requires
from apps.courses import access as course_access

from . import policies, services
from .serializers import (
    AcademicEventSerializer,
    AcademicEventWriteSerializer,
    EffectivePolicySerializer,
    PolicySerializer,
    PolicyWriteSerializer,
)

ACADEMICS_TAG = ["academic configuration"]


class EffectivePolicyView(APIView):
    """What the rules resolve to right now.

    The endpoint a dashboard reads. Optionally scoped to a course, so a student
    sees the rules for the course they are on rather than the institution's
    defaults.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Rules in force",
        responses={200: EffectivePolicySerializer},
        tags=ACADEMICS_TAG,
    )
    def get(self, request):
        course = None
        course_id = request.query_params.get("course")
        if course_id:
            course = get_object_or_404(course_access.visible_courses(request.user), pk=course_id)
        resolved = policies.policy_for(course)
        return Response(EffectivePolicySerializer(resolved.as_dict()).data)


class GlobalPolicyView(APIView):
    """The institution-wide rules."""

    permission_classes = (requires(Capability.ACADEMIC_CONFIGURE),)

    @extend_schema(
        summary="Institution-wide rules", responses={200: PolicySerializer}, tags=ACADEMICS_TAG
    )
    def get(self, request):
        return Response(PolicySerializer(services.get_or_create_policy()).data)

    @extend_schema(
        summary="Change the institution-wide rules",
        request=PolicyWriteSerializer,
        responses={200: PolicySerializer},
        tags=ACADEMICS_TAG,
    )
    def patch(self, request):
        serializer = PolicyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = services.update_policy(
            policy=services.get_or_create_policy(),
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(PolicySerializer(policy).data)


class CoursePolicyView(APIView):
    """A course's overrides. Unset fields inherit the institution's rules."""

    permission_classes = (requires(Capability.ACADEMIC_CONFIGURE),)

    def _course(self, request, course_id):
        return get_object_or_404(course_access.visible_courses(request.user), pk=course_id)

    @extend_schema(
        summary="Course rule overrides", responses={200: PolicySerializer}, tags=ACADEMICS_TAG
    )
    def get(self, request, course_id):
        course = self._course(request, course_id)
        return Response(PolicySerializer(services.get_or_create_policy(course=course)).data)

    @extend_schema(
        summary="Change a course's rule overrides",
        request=PolicyWriteSerializer,
        responses={200: PolicySerializer},
        tags=ACADEMICS_TAG,
    )
    def patch(self, request, course_id):
        course = self._course(request, course_id)
        serializer = PolicyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = services.update_policy(
            policy=services.get_or_create_policy(course=course),
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(PolicySerializer(policy).data)

    @extend_schema(
        summary="Remove a course's overrides",
        request=None,
        responses={204: OpenApiResponse(description="The course inherits again.")},
        tags=ACADEMICS_TAG,
    )
    def delete(self, request, course_id):
        course = self._course(request, course_id)
        services.clear_course_policy(
            policy=services.get_or_create_policy(course=course), actor=request.user
        )
        return Response(status=http_status.HTTP_204_NO_CONTENT)


class AcademicCalendarView(APIView):
    """Terms, holidays and examination weeks — §8.1.

    Readable by anyone signed in: a student is entitled to know when the term
    break is. Writable only with `ACADEMIC_CONFIGURE`, because a holiday added
    here stops classes being generated on those days.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="The academic calendar",
        responses={200: AcademicEventSerializer(many=True)},
        tags=ACADEMICS_TAG,
    )
    def get(self, request):
        from .models import AcademicEvent

        rows = AcademicEvent.objects.all()
        year = request.query_params.get("year")
        if year and year.isdigit():
            rows = rows.filter(start_date__year=int(year))
        return Response(AcademicEventSerializer(rows, many=True).data)

    @extend_schema(
        summary="Add a calendar entry",
        request=AcademicEventWriteSerializer,
        responses={201: AcademicEventSerializer},
        tags=ACADEMICS_TAG,
    )
    def post(self, request):
        from apps.accounts.roles import Capability, has_capability

        if not has_capability(request.user, Capability.ACADEMIC_CONFIGURE):
            return Response(
                {
                    "error": {
                        "code": "permission_denied",
                        "message": "You cannot change the academic calendar.",
                        "request_id": getattr(request, "request_id", "-"),
                    }
                },
                status=http_status.HTTP_403_FORBIDDEN,
            )

        serializer = AcademicEventWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = services.add_calendar_event(actor=request.user, **serializer.validated_data)
        return Response(AcademicEventSerializer(event).data, status=http_status.HTTP_201_CREATED)


class AcademicCalendarEntryView(APIView):
    permission_classes = (requires(Capability.ACADEMIC_CONFIGURE),)

    @extend_schema(
        summary="Remove a calendar entry",
        request=None,
        responses={204: OpenApiResponse(description="Removed.")},
        tags=ACADEMICS_TAG,
    )
    def delete(self, request, event_id):
        from .models import AcademicEvent

        event = get_object_or_404(AcademicEvent.objects.all(), pk=event_id)
        services.remove_calendar_event(event=event, actor=request.user)
        return Response(status=http_status.HTTP_204_NO_CONTENT)
