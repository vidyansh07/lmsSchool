from django.apps import AppConfig


class HealthConfig(AppConfig):
    """Liveness and readiness probes for orchestrators and load balancers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.health"
    verbose_name = "Health"
