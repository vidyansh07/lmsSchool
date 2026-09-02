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
