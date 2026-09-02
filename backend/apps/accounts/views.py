"""Authentication and user-administration endpoints.

Authorization is declared per view as a *capability*, resolved on the server
from the persisted role. No view reads a role from the request, and no view
trusts the client to have hidden anything.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.mixins import EnforceCSRFMixin
from apps.common.permissions import AllowAnyPublic, Capability, HasCapability, IsActiveUser
from apps.common.throttling import AuthEndpointThrottle

from . import services
from .models import User
from .serializers import (
    CurrentUserSerializer,
    DetailSerializer,
    EmailVerificationConfirmSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileImageUploadSerializer,
    SelfUserUpdateSerializer,
)

AUTH_TAG = ["auth"]


def _current_user_response(user: User) -> Response:
    return Response(CurrentUserSerializer(user).data)


@method_decorator(ensure_csrf_cookie, name="get")
class CSRFTokenView(APIView):
    """Issue the CSRF cookie a browser client needs before its first POST.

    Safe to call anonymously: the cookie is a per-session anti-forgery token,
    not a credential.
    """

    permission_classes = (AllowAnyPublic,)
    authentication_classes = ()

    @extend_schema(summary="Obtain a CSRF token", responses={200: DetailSerializer}, tags=AUTH_TAG)
    def get(self, request):
        return Response({"detail": "CSRF cookie set."})


class LoginView(EnforceCSRFMixin, APIView):
    """Session login.

    Rate limited per client IP. Failures are deliberately indistinguishable from
    one another so the endpoint cannot be used to enumerate accounts, and both
    outcomes are audited by the authentication signal receivers. CSRF is
    enforced explicitly because DRF would otherwise skip the check on an
    anonymous request (see ``EnforceCSRFMixin``).
    """

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Sign in with email and password",
        request=LoginSerializer,
        responses={
            200: CurrentUserSerializer,
            401: OpenApiResponse(description="Invalid credentials or inactive account."),
            429: OpenApiResponse(description="Too many attempts."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # `authenticate` already fired user_login_failed, which the audit
            # receiver records. One generic answer for every failure reason,
            # including "account is inactive" — otherwise the response tells an
            # attacker which addresses are real.
            return Response(
                {
                    "error": {
                        "code": "authentication_failed",
                        "message": "Invalid credentials.",
                        "request_id": getattr(request, "request_id", "-"),
                    }
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        # Fresh session key on privilege change defeats session fixation.
        request.session.cycle_key()
        return _current_user_response(user)


class LogoutView(APIView):
    """End the current session. Idempotent and CSRF-protected."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Sign out", request=None, responses={200: DetailSerializer}, tags=AUTH_TAG
    )
    def post(self, request):
        logout(request)
        return Response({"detail": "Signed out."})


class RevokeSessionsView(APIView):
    """Sign out of every device, including this one."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Sign out everywhere",
        request=None,
        responses={200: DetailSerializer},
        tags=AUTH_TAG,
    )
    def post(self, request):
        user = request.user
        logout(request)
        revoked = services.revoke_sessions(user=user, actor=user, reason="user_requested")
        return Response({"detail": f"Signed out of {revoked} session(s)."})


class MeView(APIView):
    """The authenticated caller's own account.

    The frontend uses this to decide what to render. That is a convenience for
    the interface only — every protected resource re-checks authorization on the
    server.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(summary="Current user", responses={200: CurrentUserSerializer}, tags=AUTH_TAG)
    def get(self, request):
        return _current_user_response(request.user)

    @extend_schema(
        summary="Update own account fields",
        request=SelfUserUpdateSerializer,
        responses={200: CurrentUserSerializer},
        tags=AUTH_TAG,
    )
    def patch(self, request):
        serializer = SelfUserUpdateSerializer(
            instance=request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        user = services.update_user(
            user=request.user, actor=request.user, **serializer.validated_data
        )
        return _current_user_response(user)


class PasswordChangeView(APIView):
    """Change the password of the signed-in user."""

    permission_classes = (IsActiveUser,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Change password",
        request=PasswordChangeSerializer,
        responses={200: DetailSerializer, 400: OpenApiResponse(description="Validation failed.")},
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(
            user=request.user,
            current_password=serializer.validated_data["current_password"],
            new_password=serializer.validated_data["new_password"],
            request=request,
        )
        return Response({"detail": "Password changed. Other sessions were signed out."})


class PasswordResetRequestView(EnforceCSRFMixin, APIView):
    """Start a password reset.

    Always answers 202 with the same body whether or not the address exists.
    Revealing the difference would turn this into an account-enumeration oracle.
    """

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Request a password reset link",
        request=PasswordResetRequestSerializer,
        responses={202: DetailSerializer},
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(email=serializer.validated_data["email"])
        return Response(
            {
                "detail": (
                    "If an account exists for that address, a password reset link has been sent."
                )
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PasswordResetConfirmView(EnforceCSRFMixin, APIView):
    """Complete a password reset with a single-use token."""

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Set a new password using a reset token",
        request=PasswordResetConfirmSerializer,
        responses={
            200: DetailSerializer,
            400: OpenApiResponse(description="Invalid, expired or already-used token."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_password(
            raw_token=serializer.validated_data["token"],
            new_password=serializer.validated_data["new_password"],
        )
        return Response({"detail": "Password updated. You can now sign in."})


class EmailVerificationRequestView(APIView):
    """Send (or resend) the verification link to the signed-in user."""

    permission_classes = (IsActiveUser,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Request an email verification link",
        request=None,
        responses={202: DetailSerializer},
        tags=AUTH_TAG,
    )
    def post(self, request):
        services.request_email_verification(user=request.user)
        return Response(
            {"detail": "If the address still needs verifying, a link has been sent."},
            status=status.HTTP_202_ACCEPTED,
        )


class EmailVerificationConfirmView(EnforceCSRFMixin, APIView):
    """Confirm an email address. Anonymous: the token is the proof."""

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Confirm an email address",
        request=EmailVerificationConfirmSerializer,
        responses={
            200: DetailSerializer,
            400: OpenApiResponse(description="Invalid, expired or already-used token."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_email(raw_token=serializer.validated_data["token"])
        return Response({"detail": "Email address verified."})


class ProfileImageView(APIView):
    """Upload or remove the signed-in user's profile image.

    Validation, re-encoding and safe naming happen in ``apps.common.uploads``;
    nothing the client sends is stored verbatim.
    """

    permission_classes = (IsActiveUser,)
    parser_classes = (MultiPartParser, FormParser)

    @extend_schema(
        summary="Upload a profile image",
        request=ProfileImageUploadSerializer,
        responses={200: CurrentUserSerializer, 400: OpenApiResponse(description="Rejected file.")},
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = ProfileImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_profile_image(
            user=request.user, uploaded_file=serializer.validated_data["image"]
        )
        return _current_user_response(user)

    @extend_schema(
        summary="Remove the profile image", responses={200: CurrentUserSerializer}, tags=AUTH_TAG
    )
    def delete(self, request):
        user = services.remove_profile_image(user=request.user)
        return _current_user_response(user)


class ProfileImageFileView(APIView):
    """Serve a stored profile image.

    Media is not web-served, so this view is the only way to read an uploaded
    file. Access rules: any authenticated, active user may see another user's
    profile image (names and faces are visible across the platform), but nobody
    anonymous can. The response is forced to ``image/jpeg`` and marked
    ``nosniff`` so a stored file can never be interpreted as anything else.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Fetch a user's profile image",
        responses={
            200: OpenApiResponse(description="JPEG image."),
            404: OpenApiResponse(description="No image."),
        },
        tags=["users"],
    )
    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        if not user.profile_image:
            raise Http404
        response = FileResponse(user.profile_image.open("rb"), content_type="image/jpeg")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response


class AdminProfileImageView(APIView):
    """Administrator removing another user's profile image (moderation)."""

    permission_classes = (HasCapability,)
    required_capability = Capability.USER_UPDATE_ANY

    @extend_schema(
        summary="Remove a user's profile image", responses={200: DetailSerializer}, tags=["users"]
    )
    def delete(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        services.remove_profile_image(user=user, actor=request.user)
        return Response({"detail": "Profile image removed."})


class EmailSettingsView(APIView):
    """Read-only view of how account email is configured, for the settings UI."""

    permission_classes = (IsActiveUser,)

    @extend_schema(summary="Account email status", responses={200: DetailSerializer}, tags=AUTH_TAG)
    def get(self, request):
        return Response(
            {
                "email": request.user.email,
                "is_email_verified": request.user.is_email_verified,
                "verification_link_valid_days": settings.AUTH_TOKEN_VERIFICATION_TTL_DAYS,
            }
        )
