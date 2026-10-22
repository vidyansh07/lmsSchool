"""Placement endpoints (`/api/v1/placements/`).

Reading is `placement.view_any` bounded to the caller's own centre, or the
student themself reading their own offers — resolved by
`access.visible_placements`, so a placement id from another centre gives the
same 404 a guessed id gives. Writing is `placement.manage`, checked again in
the services so the rule holds even if a view is wired wrong.

A student who tries to write is refused by the capability, not by a special
case: they hold neither `placement.manage` nor anything that implies it.
"""

from __future__ import annotations

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status as http_status
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import Capability, HasCapability, IsActiveUser
from apps.enrollments.models import Enrollment
from apps.students import access as students_access

from . import access, services
from .models import Placement, PlacementStatus
from .serializers import (
    PlacementSerializer,
    PlacementSummarySerializer,
    PlacementUpdateSerializer,
    PlacementWriteSerializer,
)

TAG = ["Placements"]


class PlacementFilterSet(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=PlacementStatus.choices)
    student = django_filters.UUIDFilter(field_name="student_id")
    company = django_filters.CharFilter(field_name="company", lookup_expr="icontains")
    #: Offers that mean a job: accepted or joined. A single `status=` cannot
    #: express it, and "how many placed" is the question this app exists for.
    placed = django_filters.BooleanFilter(method="filter_placed")
    offered_after = django_filters.DateFilter(field_name="offered_on", lookup_expr="gte")
    offered_before = django_filters.DateFilter(field_name="offered_on", lookup_expr="lte")

    class Meta:
        model = Placement
        fields = ("status", "student", "company", "placed", "offered_after", "offered_before")

    def filter_placed(self, queryset, name, value):
        from .models import PLACED_STATUSES

        if value is None:
            return queryset
        if value:
            return queryset.filter(status__in=PLACED_STATUSES)
        return queryset.exclude(status__in=PLACED_STATUSES)


class PlacementListView(ListAPIView):
    """Every offer the caller may see, newest first. Narrowing by `student`
    applies *after* the scoping, so naming somebody else's id returns nothing
    rather than their offers."""

    permission_classes = (IsActiveUser,)
    serializer_class = PlacementSerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = PlacementFilterSet
    ordering_fields = ("offered_on", "created_at", "annual_package", "company")
    ordering = ("-offered_on",)

    def get_queryset(self):
        return access.visible_placements(self.request.user)

    @extend_schema(summary="Placements and offers", tags=TAG)
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Record a placement or an offer",
        request=PlacementWriteSerializer,
        responses={201: PlacementSerializer},
        tags=TAG,
    )
    def post(self, request, *args, **kwargs):
        if not access.can_manage_placements(request.user):
            raise AuthorityError("You do not have authority to record a placement.")
        serializer = PlacementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        # Out of the caller's own visible students, not the table: a write is
        # a read as well, and a 201 against an id the caller cannot see would
        # confirm that student exists and file an offer their centre would
        # then watch appear.
        student = get_object_or_404(
            students_access.visible_students(request.user), pk=data.pop("student")
        )
        enrollment = None
        enrollment_id = data.pop("enrollment", None)
        if enrollment_id:
            enrollment = get_object_or_404(
                Enrollment.objects.filter(student=student), pk=enrollment_id
            )

        placement = services.record_placement(
            actor=request.user, student=student, enrollment=enrollment, **data
        )
        return Response(PlacementSerializer(placement).data, status=http_status.HTTP_201_CREATED)


class PlacementDetailView(APIView):
    """One offer: read it, or change it."""

    permission_classes = (IsActiveUser,)
    serializer_class = PlacementSerializer
    capability_map = {"PATCH": Capability.PLACEMENT_MANAGE}

    def _get(self, request, placement_id) -> Placement:
        return get_object_or_404(access.visible_placements(request.user), pk=placement_id)

    @extend_schema(summary="One placement", responses={200: PlacementSerializer}, tags=TAG)
    def get(self, request, placement_id):
        return Response(PlacementSerializer(self._get(request, placement_id)).data)

    @extend_schema(
        summary="Change a placement",
        request=PlacementUpdateSerializer,
        responses={200: PlacementSerializer},
        tags=TAG,
    )
    def patch(self, request, placement_id):
        placement = self._get(request, placement_id)
        if not access.can_manage_placements(request.user):
            raise AuthorityError("You do not have authority to change a placement.")
        serializer = PlacementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        if not fields:
            raise ApplicationError({"non_field_errors": ["Nothing to change."]})
        if "enrollment" in fields:
            enrollment_id = fields.pop("enrollment")
            fields["enrollment"] = (
                get_object_or_404(
                    Enrollment.objects.filter(student_id=placement.student_id), pk=enrollment_id
                )
                if enrollment_id
                else None
            )
        updated = services.update_placement(actor=request.user, placement=placement, fields=fields)
        return Response(PlacementSerializer(updated).data)


class PlacementSummaryView(APIView):
    """The workspace's opening numbers, over what the caller may see.

    `placement.view_any`, unlike the list beside it: these are the placement
    desk's own figures, and a student has no use for a count of their own
    offers that the list itself does not already give them. Narrower by
    default is the right way round for a route whose whole output is
    aggregate — see `services.summary`, which is still scoped on top.
    """

    permission_classes = (HasCapability,)
    required_capability = Capability.PLACEMENT_VIEW_ANY
    serializer_class = PlacementSummarySerializer

    @extend_schema(
        summary="Placement summary", responses={200: PlacementSummarySerializer}, tags=TAG
    )
    def get(self, request):
        return Response(PlacementSummarySerializer(services.summary(request.user)).data)
