"""Pause any active automation rule whose author has since lost a permission
one of its own actions needs (ERP Phase 14, ADR-13; `AUTOMATION_CATALOG.md`:
"a rule whose author later loses the permission is paused by sync and shown
as such"). Safe to run often — an ops cron, alongside `sync_permissions` on
deploy. The rule list view (`apps.automation.views.
AutomationRuleListCreateView`) also runs this cheaply on every read, so this
command is a belt-and-braces catch-up, not the only place it happens.
"""

from django.core.management.base import BaseCommand

from apps.automation.services import sync_rule_authors


class Command(BaseCommand):
    help = "Pause any active automation rule whose author has lost a permission it needs."

    def handle(self, *args, **options) -> None:
        paused = sync_rule_authors()
        self.stdout.write(f"automation rules paused: {paused}")
