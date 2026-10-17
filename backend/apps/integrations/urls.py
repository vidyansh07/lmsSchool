"""Integration routes (mounted at /api/v1/integrations/)."""

from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("leads/", views.LeadIntakeView.as_view(), name="leads"),
    path("presets/", views.PresetsView.as_view(), name="presets"),
    path("api-keys/", views.ApiKeyListView.as_view(), name="api-keys"),
    path("api-keys/<uuid:key_id>/", views.ApiKeyDetailView.as_view(), name="api-key"),
    path("api-keys/<uuid:key_id>/revoke/", views.ApiKeyRevokeView.as_view(), name="api-key-revoke"),
    path(
        "api-keys/<uuid:key_id>/intakes/",
        views.ApiKeyIntakesView.as_view(),
        name="api-key-intakes",
    ),
    path("webhooks/", views.WebhookListView.as_view(), name="webhooks"),
    path("webhooks/<uuid:webhook_id>/", views.WebhookDetailView.as_view(), name="webhook"),
    path("webhooks/<uuid:webhook_id>/test/", views.WebhookTestView.as_view(), name="webhook-test"),
    path(
        "webhooks/<uuid:webhook_id>/deliveries/",
        views.WebhookDeliveriesView.as_view(),
        name="webhook-deliveries",
    ),
]
