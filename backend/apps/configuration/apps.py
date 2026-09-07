from django.apps import AppConfig


class ConfigurationConfig(AppConfig):
    """Platform configuration an operator changes without a deployment.

    The institution's own name, how to reach it, whether notification email
    goes out at all, and the two operational ceilings that are a judgement
    rather than a security boundary. Deliberately *not* academic policy —
    `apps.academics` owns every rule about attendance, marks and completion,
    and a second table with the same shape would only make "where does this
    rule live?" a question.

    No ``access.py``. There is one row and no per-record question to answer, so
    authority is a capability declared on the view — the same reason
    `apps.dashboards` has none.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.configuration"
    verbose_name = "Platform configuration"
