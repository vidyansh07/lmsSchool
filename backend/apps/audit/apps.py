from django.apps import AppConfig


class AuditConfig(AppConfig):
    """Append-only record of security- and business-relevant actions."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Audit"
