from django.apps import AppConfig


class SearchConfig(AppConfig):
    """Global search: a read model, like `apps.dashboards`.

    Owns no tables. It composes hits from the domain apps' own `visible_*`
    querysets, so "can this search find it?" and "can this endpoint show it?"
    can never drift apart — the same reasoning `apps.dashboards.apps` gives
    for owning no tables of its own.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"
    verbose_name = "Search"
