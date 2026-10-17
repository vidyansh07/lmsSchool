"""What each preset pre-fills.

`LEAD_FIELDS` maps a payload's field names to enquiry fields
(`apps.enquiries.services.ANSWER_FIELDS` keys, plus `external_id`). The generic
preset accepts the enquiry's own names and a few obvious aliases; the Meritto
preset adds the names Meritto's lead export and webhooks use. A key's own
`field_map` is applied last, so an institution whose Meritto form has a custom
field can point it anywhere without a code change.
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
}

LEAD_FIELDS: dict[str, dict[str, str]] = {
    Preset.GENERIC: _GENERIC,
    Preset.MERITTO: _MERITTO,
}

#: The headers a receiver of that kind expects; the values are typed in by an
#: administrator and stored encrypted.
WEBHOOK_HEADERS: dict[str, list[str]] = {
    Preset.GENERIC: [],
    Preset.MERITTO: ["access-key", "secret-key"],
}

#: Field names in the JSON the `send_webhook` action posts, per preset. The
#: generic shape is the automation context itself; the Meritto shape flattens
#: an enquiry to the names Meritto's lead API accepts.
MERITTO_LEAD_KEYS = {
    "full_name": "name",
    "mobile": "mobile",
    "email": "email",
    "course": "course",
    "city": "city",
    "state": "state",
    "source": "source",
    "stage": "lead_stage",
}
