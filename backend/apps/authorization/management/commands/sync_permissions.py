"""Keep the permission rows equal to the code catalog (ADR-01). Run on deploy."""

from django.core.management.base import BaseCommand

from apps.audit.services import AuditAction, record
from apps.authorization.resolver import forget_roles
from apps.authorization.sync import sync_catalog


class Command(BaseCommand):
    help = "Synchronise the permission catalog and system roles with the code matrix."

    def handle(self, *args, **options) -> None:
        counts = sync_catalog()
        forget_roles()
        record(
            action=AuditAction.PERMISSIONS_SYNCED,
            actor=None,
            actor_label="system",
            resource_type="permission",
            resource_id="catalog",
            context=counts,
            durable=False,
        )
        self.stdout.write(
            "permissions: "
            + ", ".join(f"{key.replace('_', ' ')} {value}" for key, value in counts.items())
        )
