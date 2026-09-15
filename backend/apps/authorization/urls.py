from django.urls import path

from .views import PermissionListView, RoleDetailView, RoleListCreateView, RoleMatrixView

app_name = "authorization"

urlpatterns = [
    path("", RoleListCreateView.as_view(), name="list"),
    path("matrix/", RoleMatrixView.as_view(), name="matrix"),
    path("<slug:slug>/", RoleDetailView.as_view(), name="detail"),
]

permission_urlpatterns = [
    path("", PermissionListView.as_view(), name="permissions"),
]
