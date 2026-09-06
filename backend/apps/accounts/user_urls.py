"""User administration routes (mounted at /api/v1/users/)."""

from django.urls import path

from .user_views import (
    UserAuditView,
    UserCredentialActionView,
    UserDetailView,
    UserListCreateView,
    UserSetActiveView,
)
from .views import AdminProfileImageView, ProfileImageFileView

app_name = "users"

urlpatterns = [
    path("", UserListCreateView.as_view(), name="list"),
    path("<uuid:user_id>/", UserDetailView.as_view(), name="detail"),
    path("<uuid:user_id>/set-active/", UserSetActiveView.as_view(), name="set-active"),
    path(
        "<uuid:user_id>/credential-link/",
        UserCredentialActionView.as_view(),
        name="credential-link",
    ),
    path("<uuid:user_id>/audit/", UserAuditView.as_view(), name="audit"),
    path("<uuid:user_id>/profile-image/", ProfileImageFileView.as_view(), name="profile-image"),
    path(
        "<uuid:user_id>/profile-image/remove/",
        AdminProfileImageView.as_view(),
        name="profile-image-remove",
    ),
]
