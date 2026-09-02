from django.apps import AppConfig


class ClassSessionsConfig(AppConfig):
    """Actual classes: the events a schedule predicts."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sessions"
    label = "class_sessions"
    verbose_name = "Class sessions"
