"""Authentication routes (mounted at /api/v1/auth/)."""

from django.urls import path

from .views import (
    CSRFTokenView,
    EmailSettingsView,
    EmailVerificationConfirmView,
    EmailVerificationRequestView,
    LoginView,
    LogoutView,
    MeView,
    MfaRecoveryRegenerateView,
    MfaSendEmailCodeView,
    MfaTotpConfirmView,
    MfaTotpDisableView,
    MfaTotpEnrolView,
    MfaVerifyView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileImageView,
    RevokeOtherSessionsView,
    RevokeSessionsView,
    SessionDetailView,
    SessionListView,
    StepUpCodeRequestView,
    StepUpView,
)

app_name = "auth"

urlpatterns = [
    path("csrf/", CSRFTokenView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("logout-all/", RevokeSessionsView.as_view(), name="logout-all"),
    # --- Session inventory (ERP Phase 6, ADR-06) ---
    path("sessions/", SessionListView.as_view(), name="sessions"),
    path(
        "sessions/revoke-others/",
        RevokeOtherSessionsView.as_view(),
        name="sessions-revoke-others",
    ),
    path("sessions/<uuid:session_id>/", SessionDetailView.as_view(), name="sessions-detail"),
    path("step-up/", StepUpView.as_view(), name="step-up"),
    path("step-up/request-code/", StepUpCodeRequestView.as_view(), name="step-up-request-code"),
    # --- MFA (ERP Phase 5, ADR-05) ---
    path("mfa/send-email-code/", MfaSendEmailCodeView.as_view(), name="mfa-send-email-code"),
    path("mfa/verify/", MfaVerifyView.as_view(), name="mfa-verify"),
    path("mfa/totp/enrol/", MfaTotpEnrolView.as_view(), name="mfa-totp-enrol"),
    path("mfa/totp/confirm/", MfaTotpConfirmView.as_view(), name="mfa-totp-confirm"),
    path("mfa/totp/disable/", MfaTotpDisableView.as_view(), name="mfa-totp-disable"),
    path(
        "mfa/recovery/regenerate/",
        MfaRecoveryRegenerateView.as_view(),
        name="mfa-recovery-regenerate",
    ),
    path("me/", MeView.as_view(), name="me"),
    path("me/email/", EmailSettingsView.as_view(), name="email-settings"),
    path("me/profile-image/", ProfileImageView.as_view(), name="profile-image"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("email/verify/", EmailVerificationRequestView.as_view(), name="email-verify-request"),
    path(
        "email/verify/confirm/",
        EmailVerificationConfirmView.as_view(),
        name="email-verify-confirm",
    ),
]
