"""Enquiry API (``/api/v1/enquiries/``).

Reading is the caller's own enquiries plus, with `enquiry.view_any`, their
centre's (`access.visible_enquiries`). Changing one is its owner, or
`enquiry.manage` at that centre. Enquiries are created by submitting the
enquiry form (``POST /forms/enquiry/fill/``), never here, so every lead
arrives the same way and starts the same automation rules.
"""

from __future__ import annotations

import django_filters
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView, get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.roles import UserRole
from apps.common import bulk
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import IsActiveUser
from apps.common.throttling import BurstThrottle

from . import access, services
from .models import MANAGED_MESSAGE, SOURCE_CHOICES, Enquiry, EnquiryStage, LeadChannel
from .serializers import (
    EnquiryBulkRequestSerializer,
    EnquiryDetailSerializer,
    EnquiryRegisterSerializer,
    EnquirySerializer,
    EnquiryUpdateSerializer,
)

TAG = ["Enquiries"]


def _refuse_students(user) -> None:
    """Enquiries are the admissions desk's own records; a student has no
    business on these endpoints at all, so they are told so rather than
    handed an empty list."""
    if getattr(user, "role", "") == UserRole.STUDENT:
        raise AuthorityError("Enquiries are for staff.")


class EnquiryFilterSet(django_filters.FilterSet):
    stage = django_filters.ChoiceFilter(choices=EnquiryStage.choices)
    owner = django_filters.CharFilter(method="filter_owner")
    source = django_filters.CharFilter(field_name="source")
    channel = django_filters.ChoiceFilter(choices=LeadChannel.choices)
    course = django_filters.CharFilter(field_name="course")
    q = django_filters.CharFilter(method="filter_search")
    open = django_filters.BooleanFilter(method="filter_open")
    created_after = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_before = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    #: `meritto`: leads Meritto sent (read-only here). `lms`: entered in the LMS.
    managed_by = django_filters.ChoiceFilter(
        choices=(("meritto", "Meritto"), ("lms", "The LMS")), method="filter_managed_by"
    )
    #: Meritto leads not yet registered as a student: the counsellor's queue.
    ready_to_admit = django_filters.BooleanFilter(method="filter_ready_to_admit")
    #: `overdue`: an open enquiry whose follow-up time has passed.
    #: `today`: follow-up due today. `none`: open with no follow-up planned.
    follow_up = django_filters.ChoiceFilter(
        choices=(("overdue", "Overdue"), ("today", "Today"), ("none", "None planned")),
        method="filter_follow_up",
    )

    class Meta:
        model = Enquiry
        fields = ("stage", "owner", "source", "channel", "course")

    def filter_follow_up(self, queryset, name, value):
        from django.utils import timezone

        now = timezone.now()
        if value == "overdue":
            return queryset.open().filter(next_follow_up_at__lt=now)
        if value == "today":
            return queryset.filter(next_follow_up_at__date=timezone.localdate())
        if value == "none":
            return queryset.open().filter(next_follow_up_at__isnull=True)
        return queryset

    def filter_owner(self, queryset, name, value):
        if value == "me":
            return queryset.filter(owner=self.request.user)
        if value == "none":
            return queryset.filter(owner__isnull=True)
        return queryset.filter(owner_id=value)

    def filter_search(self, queryset, name, value):
        value = (value or "").strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(full_name__icontains=value) | Q(mobile__icontains=value) | Q(email__icontains=value)
        )

    def filter_open(self, queryset, name, value):
        return queryset.open() if value else queryset

    def filter_managed_by(self, queryset, name, value):
        from .models import MANAGING_SYSTEMS

        if value == "meritto":
            return queryset.filter(external_system__in=MANAGING_SYSTEMS)
        if value == "lms":
            return queryset.exclude(external_system__in=MANAGING_SYSTEMS)
        return queryset

    def filter_ready_to_admit(self, queryset, name, value):
        from .models import MANAGING_SYSTEMS

        ready = queryset.filter(external_system__in=MANAGING_SYSTEMS, student__isnull=True).open()
        return ready if value else queryset


class EnquiryListView(ListAPIView):
    permission_classes = (IsActiveUser,)
    serializer_class = EnquirySerializer
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filterset_class = EnquiryFilterSet
    ordering_fields = ("created_at", "next_follow_up_at", "stage_changed_at", "full_name")
    ordering = ("-created_at",)
    queryset = Enquiry.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Enquiry.objects.none()
        return access.visible_enquiries(self.request.user)

    @extend_schema(summary="List enquiries", tags=TAG)
    def get(self, request, *args, **kwargs):
        _refuse_students(request.user)
        return super().get(request, *args, **kwargs)


class EnquirySummaryView(APIView):
    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="How many visible enquiries are at each stage",
        responses={200: OpenApiResponse(description="{stages: {stage: count}, total}")},
        tags=TAG,
    )
    def get(self, request):
        _refuse_students(request.user)
        counts = dict(
            access.visible_enquiries(request.user)
            .order_by()
            .values_list("stage")
            .annotate(count=Count("id"))
        )
        stages = {stage: counts.get(stage, 0) for stage in EnquiryStage.values}
        by_channel = dict(
            access.visible_enquiries(request.user)
            .order_by()
            .values_list("channel")
            .annotate(count=Count("id"))
        )
        channels = {channel: by_channel.get(channel, 0) for channel in LeadChannel.values}
        from .models import MANAGING_SYSTEMS

        ready = (
            access.visible_enquiries(request.user)
            .filter(external_system__in=MANAGING_SYSTEMS, student__isnull=True)
            .open()
            .count()
        )
        return Response(
            {
                "stages": stages,
                "channels": channels,
                "ready_to_admit": ready,
                "total": sum(stages.values()),
                "sources": [{"value": value, "label": label} for value, label in SOURCE_CHOICES],
            }
        )


def _owner_for(enquiry: Enquiry, owner: User | None) -> User | None:
    """Refuse an owner who could not work the enquiry: somebody inactive, a
    student, or staff at another centre."""
    if owner is None:
        return None
    if not owner.is_active or owner.role == UserRole.STUDENT:
        raise ApplicationError({"owner": ["Choose an active member of staff."]})
    if enquiry.branch_id and owner.branch_id and owner.branch_id != enquiry.branch_id:
        raise ApplicationError({"owner": ["The owner must work at the enquiry's centre."]})
    return owner


class EnquiryDetailView(APIView):
    permission_classes = (IsActiveUser,)
    serializer_class = EnquiryDetailSerializer

    def _get(self, request, enquiry_id) -> Enquiry:
        _refuse_students(request.user)
        return get_object_or_404(access.visible_enquiries(request.user), pk=enquiry_id)

    @extend_schema(summary="One enquiry, with its history", tags=TAG)
    def get(self, request, enquiry_id):
        enquiry = self._get(request, enquiry_id)
        return Response(EnquiryDetailSerializer(enquiry, context={"request": request}).data)

    @extend_schema(
        summary="Change an enquiry",
        request=EnquiryUpdateSerializer,
        responses={200: EnquiryDetailSerializer},
        tags=TAG,
    )
    def patch(self, request, enquiry_id):
        enquiry = self._get(request, enquiry_id)
        if enquiry.is_managed_externally:
            raise ApplicationError({"non_field_errors": [MANAGED_MESSAGE]})
        if not access.can_manage_enquiry(request.user, enquiry):
            raise AuthorityError("You cannot change this enquiry.")
        serializer = EnquiryUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        if "owner" in fields:
            owner_id = fields.pop("owner")
            owner = None
            if owner_id:
                owner = User.objects.filter(pk=owner_id, is_active=True).first()
                if owner is None:
                    raise ApplicationError({"owner": ["No such active person."]})
            fields["owner"] = _owner_for(enquiry, owner)
        services.update(actor=request.user, enquiry=enquiry, fields=fields)
        return Response(
            EnquiryDetailSerializer(
                self._get(request, enquiry_id), context={"request": request}
            ).data
        )


class EnquiryBulkView(APIView):
    """Assign an owner to many enquiries at once — the ticked ones, or every
    one the list's filters match.

    Each enquiry needs the same right the single change does (its owner, or
    `enquiry.manage` at its centre), and the same owner rule (active staff
    at the enquiry's centre); one that fails either is skipped with the
    reason.
    """

    permission_classes = (IsActiveUser,)
    throttle_classes = (BurstThrottle,)

    @extend_schema(
        summary="Act on many enquiries at once",
        request=EnquiryBulkRequestSerializer,
        responses={200: bulk.BulkResultSerializer},
        tags=TAG,
    )
    def post(self, request):
        _refuse_students(request.user)
        serializer = EnquiryBulkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        owner = None
        if data.get("owner_id"):
            owner = User.objects.filter(pk=data["owner_id"], is_active=True).first()
            if owner is None or owner.role == UserRole.STUDENT:
                raise ApplicationError({"owner_id": ["Choose an active member of staff."]})

        rows, missing = bulk.resolve_targets(
            access.visible_enquiries(request.user),
            data,
            filterset="apps.enquiries.views.EnquiryFilterSet",
            request=request,
        )

        def assign(enquiry: Enquiry) -> str | None:
            if not access.can_manage_enquiry(request.user, enquiry):
                return "You cannot change this enquiry."
            if enquiry.owner_id == getattr(owner, "pk", None):
                return "Already theirs." if owner else "Already unassigned."
            services.update(
                actor=request.user, enquiry=enquiry, fields={"owner": _owner_for(enquiry, owner)}
            )
            return None

        result = bulk.apply_each(
            bulk.BulkResult(action=data["action"]),
            rows,
            missing,
            assign,
            lambda enquiry: enquiry.full_name or enquiry.mobile or str(enquiry.pk),
        )
        return Response(bulk.BulkResultSerializer(result).data)


class EnquiryRegisterView(APIView):
    """Record that the lead was registered as a student — the step the
    admissions wizard finishes with when it was opened from an enquiry."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Link an enquiry to the student it was registered as",
        request=EnquiryRegisterSerializer,
        responses={200: EnquiryDetailSerializer},
        tags=TAG,
    )
    def post(self, request, enquiry_id):
        from apps.students import access as students_access

        _refuse_students(request.user)
        enquiry = get_object_or_404(access.visible_enquiries(request.user), pk=enquiry_id)
        serializer = EnquiryRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = get_object_or_404(
            students_access.visible_students(request.user), pk=serializer.validated_data["student"]
        )
        services.link_registration(actor=request.user, enquiry=enquiry, student=student)
        refreshed = get_object_or_404(access.visible_enquiries(request.user), pk=enquiry_id)
        return Response(EnquiryDetailSerializer(refreshed, context={"request": request}).data)
