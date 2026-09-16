"""Background tasks for the activity engine.

Both tasks are thin wrappers around their `services` counterparts — the
business logic lives there, not here, so a management command or a test can
call the same function without going through Celery. Task arguments are
none at all: both sweeps scan for candidates themselves, the same shape
`apps.notifications.tasks.retry_pending_email` uses for its own sweep.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("grras.work")


@shared_task(name="work.mark_overdue", ignore_result=True)
def mark_overdue() -> dict[str, int]:
    from . import services

    result = services.mark_overdue_and_missed()
    if result["overdue"] or result["missed"]:
        logger.info("Activity sweep", extra={"context": result})
    return result


@shared_task(name="work.reminders", ignore_result=True)
def reminders() -> int:
    from . import services

    sent = services.send_activity_reminders()
    if sent:
        logger.info("Activity reminders sent", extra={"context": {"sent": sent}})
    return sent
