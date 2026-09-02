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
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileImageView,
    RevokeSessionsView,
)

app_name = "auth"

urlpatterns = [
    path("csrf/", CSRFTokenView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("logout-all/", RevokeSessionsView.as_view(), name="logout-all"),
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
