"""User administration routes (mounted at /api/v1/users/)."""

from django.urls import include, path

from apps.authorization.urls import user_scope_urlpatterns

from .user_views import (
    StaffRecordView,
    UserAuditView,
    UserBranchView,
    UserBulkView,
    UserCredentialActionView,
    UserDetailView,
    UserListCreateView,
    UserRoleTransitionView,
    UserSessionListView,
    UserSessionRevokeView,
    UserSetActiveView,
)
from .views import AdminProfileImageView, ProfileImageFileView

app_name = "users"

urlpatterns = [
    path("", UserListCreateView.as_view(), name="list"),
    path("bulk/", UserBulkView.as_view(), name="bulk"),
    path("<uuid:user_id>/", UserDetailView.as_view(), name="detail"),
    path("<uuid:user_id>/set-active/", UserSetActiveView.as_view(), name="set-active"),
    path(
        "<uuid:user_id>/role-transition/",
        UserRoleTransitionView.as_view(),
        name="role-transition",
    ),
    path(
        "<uuid:user_id>/credential-link/",
        UserCredentialActionView.as_view(),
        name="credential-link",
    ),
    path("<uuid:user_id>/audit/", UserAuditView.as_view(), name="audit"),
    path("<uuid:user_id>/record/", StaffRecordView.as_view(), name="staff-record"),
    path("<uuid:user_id>/branch/", UserBranchView.as_view(), name="branch"),
    path("<uuid:user_id>/sessions/", UserSessionListView.as_view(), name="sessions"),
    path(
        "<uuid:user_id>/sessions/<uuid:session_id>/",
        UserSessionRevokeView.as_view(),
        name="sessions-revoke",
    ),
    path(
        "<uuid:user_id>/scope-grants/",
        include((user_scope_urlpatterns, "scope-grants")),
    ),
    path("<uuid:user_id>/profile-image/", ProfileImageFileView.as_view(), name="profile-image"),
    path(
        "<uuid:user_id>/profile-image/remove/",
        AdminProfileImageView.as_view(),
        name="profile-image-remove",
    ),
]
