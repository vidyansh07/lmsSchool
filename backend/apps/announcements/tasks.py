"""Announcement scheduling's beat task (ERP Phase 19).

Registered in `config.settings.base.CELERY_BEAT_SCHEDULE` as
``announcements-publish-due``, every minute — the same registration shape
`apps.work.tasks`/`apps.performance.tasks` already use for their own beat
tasks.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("grras.announcements")


@shared_task(name="announcements.publish_due", ignore_result=True)
def publish_due() -> dict[str, int]:
    """Publish every scheduled announcement whose `publish_at` has passed.

    Idempotent and bounded (ADR-17): each row is re-read and re-checked
    immediately before `services.publish` is called, inside its own
    transaction, so a row already published by a concurrent request (or by
    a redelivered copy of this same task) is a no-op rather than a double
    fan-out; one announcement's failure never stops the sweep from trying
    the rest.
    """
    from . import services
    from .models import Announcement, AnnouncementStatus

    due_ids = list(
        Announcement.objects.filter(
            status=AnnouncementStatus.SCHEDULED, publish_at__lte=timezone.now()
        ).values_list("pk", flat=True)
    )

    published = 0
    for announcement_id in due_ids:
        announcement = Announcement.objects.filter(
            pk=announcement_id, status=AnnouncementStatus.SCHEDULED
        ).first()
        if announcement is None:
            continue
        try:
            services.publish(announcement=announcement, actor=None)
            published += 1
        except Exception:
            logger.exception(
                "Failed to auto-publish a scheduled announcement",
                extra={"context": {"announcement": str(announcement_id)}},
            )
    if published:
        logger.info(
            "Auto-published scheduled announcements", extra={"context": {"count": published}}
        )
    return {"published": published}
