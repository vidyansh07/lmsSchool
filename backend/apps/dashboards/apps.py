from django.apps import AppConfig


class DashboardsConfig(AppConfig):
    """Read models: the calendar and the role dashboards.

    This app owns no tables. It composes what a person should see right now from
    the domain apps — which is a presentation question, not a domain one, and
    keeping it out of those apps stops "what does the dashboard need?" leaking
    into models that exist for other reasons.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboards"
    verbose_name = "Dashboards"

    def ready(self) -> None:
        # Performance sweep: invalidate `dashboard:manager`/`dashboard:trainer`
        # the moment an activity completes, on the same extension point
        # `apps.automation.apps.AutomationConfig.ready()` already attaches to
        # for an unrelated reason — neither this app nor `apps.work` imports
        # the other back.
        from apps.work.signals import activity_changed

        from .receivers import on_activity_changed

        activity_changed.connect(on_activity_changed, dispatch_uid="dashboards.on_activity_changed")
