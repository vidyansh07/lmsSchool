"""What each preset pre-fills.

`LEAD_FIELDS` maps a payload's field names to enquiry fields
(`apps.enquiries.services.ANSWER_FIELDS` keys, plus the three `EXTERNAL_FIELDS`).
The generic preset accepts the enquiry's own names and a few obvious aliases;
the Meritto preset adds the names Meritto's lead export and webhooks use. A
key's own `field_map` is applied last, so an institution whose Meritto form
has a custom field can point it anywhere without a code change.

Meritto manages its leads (owner's decision, 17 October 2026): it sends a lead
when it is ready to admit, and its stage and owner arrive as Meritto's own
words — `external_stage`, `external_owner` — shown in the LMS, never mapped
onto the LMS pipeline. Nothing goes back to Meritto.
"""

from __future__ import annotations

from .models import Preset

_GENERIC = {
    "full_name": "full_name",
    "name": "full_name",
    "mobile": "mobile",
    "phone": "mobile",
    "email": "email",
    "whatsapp_number": "whatsapp_number",
    "state": "state",
    "city": "city",
    "course": "course",
    "track": "track",
    "preferred_centre": "preferred_centre",
    "mode": "mode",
    "batch_timing": "batch_timing",
    "qualification": "qualification",
    "source": "source",
    "utm_source": "utm_source",
    "utm_medium": "utm_medium",
    "utm_campaign": "utm_campaign",
    "remarks": "remarks",
    "message": "remarks",
    "external_id": "external_id",
    "id": "external_id",
}

#: Targets that are not enquiry form answers: kept on the enquiry as the
#: sending system's own record of the lead.
EXTERNAL_FIELDS = frozenset({"external_id", "external_stage", "external_owner"})

_MERITTO = {
    **_GENERIC,
    "lead_id": "external_id",
    "leadId": "external_id",
    "student_name": "full_name",
    "mobile_number": "mobile",
    "phone_number": "mobile",
    "email_id": "email",
    "course_name": "course",
    "program": "course",
    "specialization": "track",
    "lead_source": "source",
    "source_name": "source",
    "campaign": "utm_campaign",
    "medium": "utm_medium",
    "highest_qualification": "qualification",
    "remark": "remarks",
    "lead_stage": "external_stage",
    "stage": "external_stage",
    "lead_status": "external_stage",
    "status": "external_stage",
    "lead_owner": "external_owner",
    "owner": "external_owner",
    "counsellor": "external_owner",
    "counselor": "external_owner",
    "assigned_to": "external_owner",
}

LEAD_FIELDS: dict[str, dict[str, str]] = {
    Preset.GENERIC: _GENERIC,
    Preset.MERITTO: _MERITTO,
}
