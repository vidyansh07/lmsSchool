"""Branding endpoints (`/api/v1/branding/`)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import Capability, HasCapability, IsActiveUser

from . import services
from .models import BrandingSetting
from .serializers import BrandingSerializer, BrandingUpdateSerializer

BRANDING_TAG = ["branding"]


class BrandingView(APIView):
    """Read the institution's appearance; change it if you may.

    Readable by any signed-in user, because every screen needs it to draw
    itself — withholding it would mean the interface renders in the wrong
    colours for anyone but an administrator, which is a worse outcome than the
    non-secret it protects.

    Writing is `platform.configure`, which only a superadmin holds. A brand
    colour is not an academic rule and not an operational one; it is the
    institution's identity, and changing it changes what every user sees.
    """

    permission_classes = (IsActiveUser,)

    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT"):
            return [HasCapability()]
        return [IsActiveUser()]

    # Read by `HasCapability` for the write methods only; the GET is open to any
    # signed-in caller through `get_permissions` above.
    required_capability = Capability.PLATFORM_CONFIGURE

    @extend_schema(
        summary="The institution's branding",
        responses={200: BrandingSerializer},
        tags=BRANDING_TAG,
    )
    def get(self, request):
        return Response(BrandingSerializer(BrandingSetting.current()).data)

    @extend_schema(
        summary="Change the institution's branding",
        request=BrandingUpdateSerializer,
        responses={200: BrandingSerializer},
        tags=BRANDING_TAG,
    )
    def patch(self, request):
        serializer = BrandingUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        branding = services.update_branding(actor=request.user, **serializer.validated_data)
        return Response(BrandingSerializer(branding).data)
