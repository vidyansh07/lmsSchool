from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Cross-cutting building blocks reused by every domain app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = "Common"
