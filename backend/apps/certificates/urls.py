"""Certificate routes.

`public_urlpatterns` is mounted outside the authenticated tree — verification is
anonymous by definition (§6.8).
"""

from __future__ import annotations

from django.urls import path

from . import views

certificate_urlpatterns = [
    path("", views.CertificateListView.as_view(), name="certificate-list"),
    path("mine/", views.MyCertificatesView.as_view(), name="certificate-mine"),
    path("templates/", views.TemplateListView.as_view(), name="certificate-templates"),
    path(
        "templates/<uuid:template_id>/",
        views.TemplateDetailView.as_view(),
        name="certificate-template-detail",
    ),
    path(
        "enrollments/<uuid:enrollment_id>/issue/",
        views.IssueCertificateView.as_view(),
        name="certificate-issue",
    ),
    path(
        "<uuid:certificate_id>/",
        views.CertificateDetailView.as_view(),
        name="certificate-detail",
    ),
    path(
        "<uuid:certificate_id>/pdf/",
        views.CertificatePdfView.as_view(),
        name="certificate-pdf",
    ),
    path(
        "<uuid:certificate_id>/reissue/",
        views.ReissueCertificateView.as_view(),
        name="certificate-reissue",
    ),
    path(
        "<uuid:certificate_id>/revoke/",
        views.RevokeCertificateView.as_view(),
        name="certificate-revoke",
    ),
    path(
        "<uuid:certificate_id>/verification-link/",
        views.VerificationLinkView.as_view(),
        name="certificate-verification-link",
    ),
]

public_urlpatterns = [
    path("<str:code>/", views.VerifyCertificateView.as_view(), name="certificate-verify"),
]
