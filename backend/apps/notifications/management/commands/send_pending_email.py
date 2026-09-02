"""Drain the outbox by hand.

Phase 9 gave this a scheduled owner: `notifications.retry_pending_email` runs on
Celery beat every few minutes and is the mechanism. This command remains as the
operator's handle on the same work — for a deployment running without beat, and
for the moment during an incident when somebody needs to flush the queue now and
watch what happens. It calls the same task, so there is one implementation and
no second copy to drift.

Bounded on purpose: a run sends at most `--limit` messages, so a backlog after
an outage drains steadily instead of hammering a provider that has just come
back.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.notifications.tasks import retry_pending_email


class Command(BaseCommand):
    help = "Attempt delivery of queued and failed email messages."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options) -> None:
        # Run here in this process, not queued: the operator asked to see the
        # outcome, and a queued sweep would print nothing useful.
        outcome = retry_pending_email(options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"Sent {outcome['sent']}, failed {outcome['failed']}.")
        )
