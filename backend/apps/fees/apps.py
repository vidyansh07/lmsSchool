from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fees"
    verbose_name = "Fees"

    def ready(self) -> None:
        from .mail import register_attachments

        register_attachments()
