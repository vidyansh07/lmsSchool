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
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.common.permissions import IsActiveUser

from . import access, services
from .models import Enquiry, EnquiryStage
from .serializers import EnquiryDetailSerializer, EnquirySerializer, EnquiryUpdateSerializer

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
    course = django_filters.CharFilter(field_name="course")
    q = django_filters.CharFilter(method="filter_search")
    open = django_filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Enquiry
        fields = ("stage", "owner", "source", "course")

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
        return Response({"stages": stages, "total": sum(stages.values())})


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
                if enquiry.branch_id and owner.branch_id and owner.branch_id != enquiry.branch_id:
                    raise ApplicationError(
                        {"owner": ["The owner must work at the enquiry's centre."]}
                    )
            fields["owner"] = owner
        services.update(actor=request.user, enquiry=enquiry, fields=fields)
        return Response(
            EnquiryDetailSerializer(
                self._get(request, enquiry_id), context={"request": request}
            ).data
        )
