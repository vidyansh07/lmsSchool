"""Background dispatch for `Delivery` rows (ERP Phase 19).

One task, mirroring `apps.notifications.tasks.send_queued_email`'s own
split exactly: the task re-reads the row and checks its state before doing
anything (`task_acks_late` makes redelivery possible, so this is what turns
a re-delivered task into a no-op instead of a second send), and the actual
per-channel work lives in `services.dispatch_delivery`, not here, so a
management command or a test can call the same function without going
through Celery.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger("grras.communication")


@shared_task(name="communication.dispatch_delivery", ignore_result=True)
def dispatch_delivery(delivery_id: str) -> bool:
    from .models import Delivery, DeliveryState
    from .services import dispatch_delivery as dispatch

    delivery = (
        Delivery.objects.select_related("template_version__template", "recipient")
        .filter(pk=delivery_id)
        .first()
    )
    if delivery is None:
        # The transaction that created it rolled back. Nothing to do.
        return False
    if delivery.state not in (DeliveryState.QUEUED, DeliveryState.PROCESSING):
        # Already dispatched, or cancelled after being queued.
        return False
    dispatch(delivery)
    return True
