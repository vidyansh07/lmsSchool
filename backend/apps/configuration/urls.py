"""Institution settings routes. `config/api_urls.py` owns the mount point."""

from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    # The literal segment is declared first, so it cannot be shadowed if this
    # list ever grows a converter route.
    path("public/", views.PublicSettingsView.as_view(), name="settings-public"),
    path("", views.SystemSettingView.as_view(), name="settings"),
]
