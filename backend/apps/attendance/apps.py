from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    """Who was in the room."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attendance"
    verbose_name = "Attendance"
