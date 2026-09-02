from django.apps import AppConfig


class StudentsConfig(AppConfig):
    """Student domain: the profile attached to a user with the student role."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.students"
    verbose_name = "Students"
