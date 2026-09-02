from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Identity: users, roles and authentication."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        # Registers the authentication audit signal receivers.
        from . import signals  # noqa: F401
