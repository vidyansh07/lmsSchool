from django.apps import AppConfig


class BatchesConfig(AppConfig):
    """Delivery: cohorts running a course, and when they meet."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.batches"
    verbose_name = "Batches"
