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
        from apps.dsr.signals import dsr_missing, dsr_submitted
        from apps.enquiries.signals import enquiry_changed
        from apps.forms.signals import form_submitted
        from apps.performance.signals import RISK_CHANGED
        from apps.work.signals import activity_changed

        from .receivers import (
            on_activity_changed,
            on_dsr_missing,
            on_dsr_submitted,
            on_enquiry_changed,
            on_form_submitted,
            on_risk_changed,
        )

        activity_changed.connect(on_activity_changed, dispatch_uid="automation.on_activity_changed")
        RISK_CHANGED.connect(on_risk_changed, dispatch_uid="automation.on_risk_changed")
        # `apps.forms.signals.form_submitted`: a form sent to someone (or
        # filled in directly) was submitted — the `FORM_SUBMITTED` trigger.
        form_submitted.connect(on_form_submitted, dispatch_uid="automation.on_form_submitted")
        # `apps.enquiries.signals.enquiry_changed`: a lead was captured or
        # changed — the three `ENQUIRY_*` triggers.
        enquiry_changed.connect(on_enquiry_changed, dispatch_uid="automation.on_enquiry_changed")
        # `apps.dsr.signals`: a class report handed in, or gone missing.
        dsr_submitted.connect(on_dsr_submitted, dispatch_uid="automation.on_dsr_submitted")
        dsr_missing.connect(on_dsr_missing, dispatch_uid="automation.on_dsr_missing")
