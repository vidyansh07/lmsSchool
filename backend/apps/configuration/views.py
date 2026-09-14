"""Institution settings API.

Changing the settings needs ``SETTINGS_MANAGE``, which sits on the
administrator rung: the institution's own name and support address are an
administrator's to keep current, and waiting on a superadmin to correct a phone
number is how a support address stays wrong.

Reading the *public* three is open to anyone signed in, because a person who
needs help needs to know where to write, and a screen that cannot say so is the
reason they call the wrong number instead.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.roles import Capability
from apps.common.caching import DAY, remember
from apps.common.permissions import HasCapability, IsActiveUser

from . import services
from .models import SystemSetting
from .serializers import (
    PublicSettingsSerializer,
    SystemSettingSerializer,
    SystemSettingWriteSerializer,
)
from .settings_resolver import effective_settings, resolve_from

SETTINGS_TAG = ["institution settings"]


def _settings_payload(row: SystemSetting | None) -> dict[str, Any]:
    """The settings in force, plus who last changed them.

    Resolved from the row the caller already read rather than through
    :func:`effective_settings`, so the screen costs one query rather than two —
    and through the same fallback the rest of the system uses, so it cannot
    show an administrator something different from what an email will say.

    Spread from :meth:`EffectiveSettings.as_dict` rather than assembled key by
    key, so a setting added to the registry cannot be forgotten here and
    silently vanish from the one screen that exists to change it.
    """
    return {
        **resolve_from(row).as_dict(),
        "updated_by_name": getattr(row.updated_by, "full_name", None) if row else None,
        "updated_at": row.updated_at if row else None,
    }


class SystemSettingView(APIView):
    """Read and change the institution's settings."""

    permission_classes = (HasCapability,)
    # `capability_map`, not `requires(...)`: `requires` is invisible to the
    # authorization sweep's `_declared_capabilities`, so the "a role without the
    # capability is refused" check would skip the one route whose whole purpose
    # is changing what every other screen renders.
    capability_map = {
        "GET": Capability.SETTINGS_MANAGE,
        "PATCH": Capability.SETTINGS_MANAGE,
    }

    @extend_schema(
        summary="The institution's settings",
        responses={200: SystemSettingSerializer},
        tags=SETTINGS_TAG,
    )
    def get(self, request):
        # `first()`, never `get_or_create`: reading the settings must not write
        # a row. Two administrators opening this screen in the same second
        # would otherwise race the `systemsetting_one_row` constraint and one
        # of them would see a 500 on a page they only looked at.
        row = SystemSetting.objects.select_related("updated_by").first()
        return Response(SystemSettingSerializer(_settings_payload(row)).data)

    @extend_schema(
        summary="Change the institution's settings",
        request=SystemSettingWriteSerializer,
        responses={200: SystemSettingSerializer},
        tags=SETTINGS_TAG,
    )
    def patch(self, request):
        serializer = SystemSettingWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings_row = services.update_settings(
            settings_row=services.get_or_create_settings(),
            actor=request.user,
            **serializer.validated_data,
        )
        # The saved row, resolved: what comes back is what the next request
        # will see, which is what makes it safe for the form to adopt the
        # response as its new baseline.
        return Response(SystemSettingSerializer(_settings_payload(settings_row)).data)


class PublicSettingsView(APIView):
    """Who the institution is, and how to reach it.

    Behind `IsActiveUser` rather than `AllowAnyPublic`: nothing here needs to be
    readable before sign-in, and a new unauthenticated surface is a thing a
    security review has to account for in exchange for nothing.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Institution name and support contact",
        operation_id="settings_public_retrieve",
        responses={200: PublicSettingsSerializer},
        tags=SETTINGS_TAG,
    )
    def get(self, request):
        def build():
            resolved = effective_settings()
            # Built key by key rather than handed `as_dict()`: `StrictSerializer` is
            # strict on input and silent on output, so passing the whole thing would
            # drop the administrative keys with no error and leave this class doing
            # nothing visible the day somebody widened it.
            return PublicSettingsSerializer(
                {
                    "institution_name": resolved.institution_name,
                    "support_email": resolved.support_email,
                    "support_phone": resolved.support_phone,
                }
            ).data

        return Response(remember("settings:public", (), DAY, build))
