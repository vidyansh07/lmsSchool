from django.apps import AppConfig


class WorkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.work"
    verbose_name = "Work (activities)"

    def ready(self) -> None:
        # Registers the `activity_changed` receivers this app ships with its
        # own signal (none yet — Phases 13/14 attach theirs here or in their
        # own apps). Importing the module is enough to keep the signal object
        # stable at `apps.work.signals.activity_changed` for other apps to
        # import from.
        from . import signals  # noqa: F401
