"""Health routes.

Unversioned on purpose: orchestrators, load balancers and uptime monitors
should not have to be reconfigured when the API version changes.
"""

from django.urls import path

from .views import liveness, readiness

app_name = "health"

urlpatterns = [
    path("live/", liveness, name="live"),
    path("ready/", readiness, name="ready"),
]
