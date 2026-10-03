"""Form and activity answers flowing onto an enquiry.

Both receivers run synchronously inside the sender's transaction, so the
enquiry an enquiry form creates is already linked to its assignment when
the automation engine (which dispatches on commit) reads it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("grras.enquiries")


def on_form_submitted(sender, *, assignment, actor=None, **kwargs) -> None:
    from apps.forms.models import FormEntity

    from . import services

    if assignment.definition.entity != FormEntity.ENQUIRY or not assignment.response_id:
        return
    values = assignment.response.values or {}
    if assignment.enquiry_id:
        services.apply_answers(actor=actor, enquiry=assignment.enquiry, values=values)
        return
    if values.get("full_name") and values.get("mobile"):
        enquiry, _created = services.capture(actor=actor, values=values, branch=assignment.branch)
        assignment.enquiry = enquiry
        assignment.save(update_fields=["enquiry", "updated_at"])


def on_activity_changed(sender, *, activity, event, actor=None, **kwargs) -> None:
    if event != "completed" or not activity.enquiry_id or not activity.form_response_id:
        return
    from . import services

    services.apply_answers(
        actor=actor, enquiry=activity.enquiry, values=activity.form_response.values or {}
    )
