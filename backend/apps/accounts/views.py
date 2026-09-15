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
from drf_spectacular.utils import OpenApiResponse, PolymorphicProxySerializer, extend_schema
from rest_framework import exceptions, status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditAction, AuditResult
from apps.audit.services import record
from apps.common.middleware import client_ip
from apps.common.mixins import EnforceCSRFMixin
from apps.common.permissions import AllowAnyPublic, Capability, HasCapability, IsActiveUser
from apps.common.throttling import AuthEndpointThrottle

from . import mfa, services
from .models import User
from .serializers import (
    CurrentUserSerializer,
    DetailSerializer,
    EmailVerificationConfirmSerializer,
    LoginSerializer,
    MfaEnrolSerializer,
    MfaRequiredSerializer,
    MfaTotpConfirmSerializer,
    MfaVerifySerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileImageUploadSerializer,
    RecoveryCodesSerializer,
    SelfUserUpdateSerializer,
    StepUpSerializer,
)
from .stepup import StepUpRequired, is_fresh

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

    ADR-05 (Phase 5): a correct password does not always finish the sign-in.
    When the account has a confirmed MFA device, or its role is required to
    use one by policy and it is past its grace period
    (:func:`apps.accounts.mfa.is_required`), ``django.contrib.auth.login`` is
    never called here — instead the session is marked pending
    (:func:`apps.accounts.mfa.start_pending`) and the response names which
    methods can complete it. Every other endpoint already treats a pending
    session as anonymous, because it is: nothing has authenticated it yet.
    """

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Sign in with email and password",
        request=LoginSerializer,
        responses={
            # No discriminator: the two shapes share no common field to key
            # on ("mfa_required" only appears in one of them), so this is a
            # plain `oneOf` rather than a discriminated union.
            200: PolymorphicProxySerializer(
                component_name="LoginResponse",
                serializers=[CurrentUserSerializer, MfaRequiredSerializer],
                resource_type_field_name=None,
            ),
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

        if mfa.is_required(user=user):
            mfa.start_pending(request=request, user=user)
            methods = mfa.available_methods(user=user)
            record(
                action=AuditAction.LOGIN_PENDING,
                actor=user,
                resource_type="user",
                resource_id=user.pk,
                context={"methods": methods},
                durable=False,
            )
            return Response(
                {
                    "mfa_required": True,
                    "methods": methods,
                    "expires_in": mfa.PENDING_TTL_SECONDS,
                }
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


class StepUpView(APIView):
    """Prove it is still you (ADR-05): a password re-entry, or an emailed
    one-time code — exactly one. Phase 5 adds TOTP and recovery codes as
    further alternatives. Sets a timestamp in the session that dangerous
    endpoints check for freshness."""

    permission_classes = (IsActiveUser,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Step-up authentication",
        request=StepUpSerializer,
        responses={
            204: None,
            400: OpenApiResponse(description="Neither or both of password/code were sent."),
            403: OpenApiResponse(description="Wrong password, or wrong/expired/void code."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = StepUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from .stepup import require_step_up

        data = serializer.validated_data
        require_step_up(
            request,
            password=data.get("password"),
            code=data.get("code"),
            method=data.get("method"),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class StepUpCodeRequestView(APIView):
    """Email a one-time code (ADR-05) for step-up — the alternative to
    re-entering the password. Always sent to the caller's own registered
    address; there is no way to name anyone else's."""

    permission_classes = (IsActiveUser,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "otp"

    @extend_schema(
        summary="Request a step-up one-time code by email",
        request=None,
        responses={
            202: DetailSerializer,
            429: OpenApiResponse(description="Too many requests — wait and retry."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        from .otp import OtpPurpose, send_email_code

        send_email_code(
            user=request.user, purpose=OtpPurpose.STEP_UP, request_ip=client_ip(request)
        )
        return Response(
            {"detail": "A one-time code has been sent to your email."},
            status=status.HTTP_202_ACCEPTED,
        )


def _resolve_mfa_target(request) -> tuple[User, str]:
    """Who the next MFA action is for, and why.

    Two contexts share these endpoints (ADR-05): a pending sign-in — the
    session holds ``mfa_pending`` and ``request.user`` is anonymous, since
    ``login()`` is never called until verification succeeds — or an already
    signed-in caller reaching for step-up. Checked in that order: a pending
    marker always wins, so a browser that happens to hold an unrelated
    authenticated session in another tab cannot shadow the sign-in in
    progress.
    """
    pending_user = mfa.get_pending_user(request=request)
    if pending_user is not None:
        return pending_user, "login"
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_active:
        return user, "step_up"
    raise exceptions.NotAuthenticated()


class MfaSendEmailCodeView(EnforceCSRFMixin, APIView):
    """Email a one-time code (ADR-05) as one of the three MFA factors.

    Works two ways, resolved by :func:`_resolve_mfa_target`: against a
    pending sign-in (before ``login()`` has ever been called — see
    ``LoginView``), or against an already-authenticated caller reaching for
    step-up, reusing exactly the send path Phase 4's
    ``StepUpCodeRequestView`` uses. Anonymous is allowed on purpose: a
    pending session, by construction, is not authenticated yet — which is
    exactly why it needs :class:`EnforceCSRFMixin` explicitly (see that
    mixin's docstring): DRF only checks CSRF once ``SessionAuthentication``
    finds a logged-in user, so an anonymous-permitted POST is unprotected by
    default. Without this, a cross-site page could spam an OTP to a
    pending-login victim's inbox using nothing but their pending-session
    cookie.
    """

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "otp"

    @extend_schema(
        summary="Email an MFA one-time code",
        request=None,
        responses={
            204: None,
            401: OpenApiResponse(description="No pending sign-in and not authenticated."),
            429: OpenApiResponse(description="Too many requests — wait and retry."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        from .otp import OtpPurpose, send_email_code

        target, purpose = _resolve_mfa_target(request)
        otp_purpose = OtpPurpose.LOGIN if purpose == "login" else OtpPurpose.STEP_UP
        send_email_code(user=target, purpose=otp_purpose, request_ip=client_ip(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaVerifyView(EnforceCSRFMixin, APIView):
    """Complete a pending sign-in, or obtain step-up, with one of the three
    MFA factors (ADR-05). Which of the two this call is doing is decided the
    same way :class:`MfaSendEmailCodeView` decides it — a pending session
    wins over an authenticated one.

    Every failure — wrong TOTP, an already-used recovery code, an expired
    email code, no device at all — answers the same generic ``400
    invalid_code``: SECURITY_DECISIONS is explicit that no method's failure
    reason may be distinguishable from another's, by message or otherwise.
    """

    permission_classes = (AllowAnyPublic,)
    throttle_classes = (AuthEndpointThrottle,)
    throttle_scope = "auth"

    @extend_schema(
        summary="Verify an MFA code",
        request=MfaVerifySerializer,
        responses={
            200: CurrentUserSerializer,
            400: OpenApiResponse(description="Wrong or expired code (never says which factor)."),
            401: OpenApiResponse(description="No pending sign-in and not authenticated."),
            429: OpenApiResponse(description="Too many attempts."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = MfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        method = serializer.validated_data["method"]
        code = serializer.validated_data["code"]

        target, purpose = _resolve_mfa_target(request)
        verified = mfa.verify(
            user=target,
            method=method,
            code=code,
            purpose=purpose,
            request_ip=client_ip(request),
        )
        if not verified:
            record(
                action=AuditAction.MFA_FAILED,
                actor=target,
                resource_type="user",
                resource_id=target.pk,
                result=AuditResult.FAILURE,
                context={"method": method, "purpose": purpose},
            )
            raise mfa.InvalidMfaCode()

        if purpose == "login":
            login(request, target)
            request.session.cycle_key()
            mfa.clear_pending(request=request)
        else:
            from .stepup import grant

            grant(request)

        record(
            action=AuditAction.MFA_VERIFIED,
            actor=target,
            resource_type="user",
            resource_id=target.pk,
            context={"method": method, "purpose": purpose},
            durable=False,
        )
        if method == "recovery":
            record(
                action=AuditAction.MFA_RECOVERY_USED,
                actor=target,
                resource_type="user",
                resource_id=target.pk,
                context={"purpose": purpose},
                durable=False,
            )
        return _current_user_response(target)


class MfaTotpEnrolView(APIView):
    """Begin (or restart) TOTP enrolment (ADR-05).

    Returns an unconfirmed device's provisioning URI, its raw secret (for
    manual entry when a camera is unavailable) and a QR code as inline SVG.
    None of the three is stored anywhere in plaintext, logged, or audited —
    this is the one response that ever carries the secret.
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Begin TOTP enrolment",
        request=None,
        responses={
            200: MfaEnrolSerializer,
            409: OpenApiResponse(description="MFA is already enabled; disable it first."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        _device, secret = mfa.start_enrolment(user=request.user)
        uri = mfa.provisioning_uri(user=request.user, secret=secret)
        return Response(
            MfaEnrolSerializer(
                {"secret_uri": uri, "secret": secret, "qr_svg": mfa.qr_svg(uri)}
            ).data
        )


class MfaTotpConfirmView(APIView):
    """Confirm TOTP enrolment with a code from the app (ADR-05).

    On success the device becomes active and ten recovery codes are issued
    and returned — the only time they are ever retrievable. The user is
    emailed (bypassing notification preferences: this is a security event,
    not a subscription — see ``apps.accounts.mfa._security_email``).
    """

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Confirm TOTP enrolment",
        request=MfaTotpConfirmSerializer,
        responses={
            200: RecoveryCodesSerializer,
            400: OpenApiResponse(description="Wrong code, or no pending enrolment."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        serializer = MfaTotpConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = mfa.confirm_enrolment(user=request.user, code=serializer.validated_data["code"])
        return Response(RecoveryCodesSerializer({"recovery_codes": codes}).data)


class MfaTotpDisableView(APIView):
    """Turn MFA off (ADR-05): deletes the device and every recovery code —
    genuinely, not a soft delete (a restorable MFA bypass would be a real
    vulnerability). Requires a fresh step-up, the same pattern
    ``LockPermissionView`` uses: refuse with ``403 step_up_required`` and let
    the interface open the step-up dialog and retry."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Disable MFA",
        request=None,
        responses={
            204: None,
            400: OpenApiResponse(description="MFA is not enabled."),
            403: OpenApiResponse(description="Step-up required."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        if not is_fresh(request):
            raise StepUpRequired()
        mfa.disable(user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MfaRecoveryRegenerateView(APIView):
    """Invalidate every existing recovery code and issue ten new ones
    (ADR-05), shown exactly once. Requires a fresh step-up, same pattern as
    :class:`MfaTotpDisableView`."""

    permission_classes = (IsActiveUser,)

    @extend_schema(
        summary="Regenerate recovery codes",
        request=None,
        responses={
            200: RecoveryCodesSerializer,
            400: OpenApiResponse(description="MFA is not enabled."),
            403: OpenApiResponse(description="Step-up required."),
        },
        tags=AUTH_TAG,
    )
    def post(self, request):
        if not is_fresh(request):
            raise StepUpRequired()
        codes = mfa.regenerate_recovery_codes(user=request.user)
        return Response(RecoveryCodesSerializer({"recovery_codes": codes}).data)


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
