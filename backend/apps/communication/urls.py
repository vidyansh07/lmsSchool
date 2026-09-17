"""Communication centre routes (ERP Phase 19).

Three separate pattern lists, mirroring `apps.work.urls`'s own shape,
because the contract mounts them at three different prefixes:
`templates/`, `deliveries/` and `communication/`.
"""

from __future__ import annotations

from django.urls import path

from . import views
from .webhooks import WhatsAppWebhookView

app_name = "communication"

template_patterns = [
    path("", views.TemplateListCreateView.as_view(), name="template-list"),
    path("<str:key>/", views.TemplateDetailView.as_view(), name="template-detail"),
    path(
        "<str:key>/versions/",
        views.TemplateVersionCreateView.as_view(),
        name="template-version-create",
    ),
    path(
        "<str:key>/versions/<int:number>/",
        views.TemplateVersionDetailView.as_view(),
        name="template-version-detail",
    ),
    path(
        "<str:key>/versions/<int:number>/approve/",
        views.TemplateVersionApproveView.as_view(),
        name="template-version-approve",
    ),
    path(
        "<str:key>/versions/<int:number>/publish/",
        views.TemplateVersionPublishView.as_view(),
        name="template-version-publish",
    ),
    path(
        "<str:key>/versions/<int:number>/preview/",
        views.TemplateVersionPreviewView.as_view(),
        name="template-version-preview",
    ),
    path(
        "<str:key>/versions/<int:number>/test-send/",
        views.TemplateVersionTestSendView.as_view(),
        name="template-version-test-send",
    ),
]

delivery_patterns = [
    path("", views.DeliveryListView.as_view(), name="delivery-list"),
    path("<uuid:delivery_id>/retry/", views.DeliveryRetryView.as_view(), name="delivery-retry"),
    path("<uuid:delivery_id>/cancel/", views.DeliveryCancelView.as_view(), name="delivery-cancel"),
]

communication_patterns = [
    path("send/", views.ManualSendView.as_view(), name="send"),
    path("whatsapp/webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
]
