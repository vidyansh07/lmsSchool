from django.urls import path

from .views import (
    LockPermissionView,
    PermissionListView,
    RoleDetailView,
    RoleListCreateView,
    RoleMatrixView,
    ScopeGrantDetailView,
    ScopeGrantListView,
    UnlockPermissionView,
)

app_name = "authorization"

urlpatterns = [
    path("", RoleListCreateView.as_view(), name="list"),
    path("matrix/", RoleMatrixView.as_view(), name="matrix"),
    path("<slug:slug>/", RoleDetailView.as_view(), name="detail"),
    path(
        "<slug:slug>/permissions/<str:code>/lock/",
        LockPermissionView.as_view(),
        name="lock",
    ),
    path(
        "<slug:slug>/permissions/<str:code>/unlock/",
        UnlockPermissionView.as_view(),
        name="unlock",
    ),
]

user_scope_urlpatterns = [
    path("", ScopeGrantListView.as_view(), name="scope-grants"),
    path("<uuid:grant_id>/", ScopeGrantDetailView.as_view(), name="scope-grant-detail"),
]

permission_urlpatterns = [
    path("", PermissionListView.as_view(), name="permissions"),
]
