from django.apps import AppConfig


class PerformanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.performance"
    verbose_name = "Performance and reviews"

    def ready(self) -> None:
        # ERP Phase 13 (ADR-11): the risk engine's receiver on
        # `apps.work.signals.activity_changed` — see `receivers.py`.
        from apps.work.signals import activity_changed

        from .receivers import on_activity_changed

        activity_changed.connect(
            on_activity_changed, dispatch_uid="performance.risk.on_activity_changed"
        )
