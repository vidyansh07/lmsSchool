from django.urls import path

from .views import (
    AutomationRuleActivateView,
    AutomationRuleDetailView,
    AutomationRuleDryRunView,
    AutomationRuleListCreateView,
    AutomationRulePauseView,
    AutomationRuleRunsView,
    AutomationRuleSummaryView,
)

app_name = "automation"

urlpatterns = [
    path("", AutomationRuleListCreateView.as_view(), name="list"),
    # Before the identifier route, which would otherwise swallow it.
    path("summary/", AutomationRuleSummaryView.as_view(), name="summary"),
    path("<uuid:pk>/", AutomationRuleDetailView.as_view(), name="detail"),
    path("<uuid:pk>/activate/", AutomationRuleActivateView.as_view(), name="activate"),
    path("<uuid:pk>/pause/", AutomationRulePauseView.as_view(), name="pause"),
    path("<uuid:pk>/dry-run/", AutomationRuleDryRunView.as_view(), name="dry-run"),
    path("<uuid:pk>/runs/", AutomationRuleRunsView.as_view(), name="runs"),
]
