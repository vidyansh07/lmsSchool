from django.apps import AppConfig


class CoursesConfig(AppConfig):
    """Course catalogue and learning content."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courses"
    verbose_name = "Courses"
