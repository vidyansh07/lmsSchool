"""Root URL configuration.

Layout:
    /admin/         Django admin (staff only)
    /health/        Liveness and readiness probes (unversioned by design:
                    orchestrators must not have to track API versions)
    /api/v1/...     Versioned JSON API
    /api/schema/    OpenAPI 3 document
    /api/docs/      Swagger UI (only where API_DOCS_ENABLED)
"""

from django.conf import settings
from django.contrib import admin
from django.db import transaction
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

handler400 = "apps.common.views.bad_request"
handler403 = "apps.common.views.permission_denied"
handler404 = "apps.common.views.not_found"
handler500 = "apps.common.views.server_error"


@transaction.non_atomic_requests
def api_root(_request):
    """Discovery document. Deliberately free of configuration details.

    Static content, so it is exempt from ``ATOMIC_REQUESTS``.
    """
    return JsonResponse(
        {
            "name": settings.PROJECT_NAME,
            "versions": {"v1": "/api/v1/"},
            "health": {"live": "/health/live/", "ready": "/health/ready/"},
            "schema": "/api/schema/",
        }
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.health.urls")),
    path("api/", api_root, name="api-root"),
    path("api/v1/", include(("config.api_urls", "v1"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]

if settings.API_DOCS_ENABLED:
    urlpatterns += [
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
    ]
