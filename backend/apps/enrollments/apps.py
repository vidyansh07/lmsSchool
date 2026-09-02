from django.apps import AppConfig


class EnrollmentsConfig(AppConfig):
    """Participation: a student's relationship with a batch, and their progress."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.enrollments"
    verbose_name = "Enrollments"
