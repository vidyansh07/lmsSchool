from django.apps import AppConfig


class EnquiriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.enquiries"
    verbose_name = "Enquiries"

    def ready(self) -> None:
        # An enquiry form answered (captured or followed up), or an activity
        # about an enquiry completed with its form, writes its mapped answers
        # onto the enquiry. Neither `apps.forms` nor `apps.work` imports this
        # app; it attaches to their own extension points.
        from apps.forms.signals import form_submitted
        from apps.work.signals import activity_changed

        from .receivers import on_activity_changed, on_form_submitted

        form_submitted.connect(on_form_submitted, dispatch_uid="enquiries.on_form_submitted")
        activity_changed.connect(on_activity_changed, dispatch_uid="enquiries.on_activity_changed")
