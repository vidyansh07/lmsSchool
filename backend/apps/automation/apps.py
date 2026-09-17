from django.apps import AppConfig


class AutomationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.automation"
    verbose_name = "Automation"

    def ready(self) -> None:
        # ERP Phase 14 (ADR-13): the automation engine's own receivers on
        # the two extension points earlier phases left for exactly this —
        # `apps.work.signals.activity_changed` (Phase 9) and
        # `apps.performance.signals.RISK_CHANGED` (Phase 13). Neither of
        # those apps imports anything back from this one.
        from apps.performance.signals import RISK_CHANGED
        from apps.work.signals import activity_changed

        from .receivers import on_activity_changed, on_risk_changed

        activity_changed.connect(on_activity_changed, dispatch_uid="automation.on_activity_changed")
        RISK_CHANGED.connect(on_risk_changed, dispatch_uid="automation.on_risk_changed")
