"""Seed two Meritto-style forms, published as version 1.

``enquiry`` is the lead-capture form a counsellor fills in for a walk-in or
phone enquiry, with the fields a Meritto lead form carries: contact
details, state and city (city depends on state), course and track (track
depends on course), centre, mode, batch timing, qualification, how they
heard about GRRAS, hidden UTM values for website traffic, remarks, and a
consent line.

``enquiry-follow-up`` is the lead status update a counsellor records after
each call: call outcome, lead stage, and the reason a lead was lost, with
each question shown only when the previous answer calls for it.

Both are ordinary definitions — an administrator edits them by creating a
version 2 in the form builder. Historical models only, idempotent, and the
reverse removes only these two definitions while nothing answered them.
"""

from __future__ import annotations

import hashlib
import json

from django.db import migrations
from django.utils import timezone


def _field(
    key,
    label,
    type_,
    *,
    required=False,
    validation=None,
    options=None,
    group="",
    help_="",
    show_if=None,
):
    return {
        "key": key,
        "label": label,
        "help": help_,
        "type": type_,
        "required": required,
        "group": group,
        "options": options if options is not None else [],
        "validation": validation or {},
        "show_if": show_if or {},
    }


def _choices(pairs):
    return [{"value": value, "label": label} for value, label in pairs]


def _select(key, label, pairs, *, required=False, group="", show_if=None, type_="select", help_=""):
    return _field(
        key,
        label,
        type_,
        required=required,
        options=_choices(pairs),
        group=group,
        show_if=show_if,
        help_=help_,
    )


OTHER = ("other", "Other")

STATES = [
    ("andhra_pradesh", "Andhra Pradesh"),
    ("arunachal_pradesh", "Arunachal Pradesh"),
    ("assam", "Assam"),
    ("bihar", "Bihar"),
    ("chhattisgarh", "Chhattisgarh"),
    ("goa", "Goa"),
    ("gujarat", "Gujarat"),
    ("haryana", "Haryana"),
    ("himachal_pradesh", "Himachal Pradesh"),
    ("jharkhand", "Jharkhand"),
    ("karnataka", "Karnataka"),
    ("kerala", "Kerala"),
    ("madhya_pradesh", "Madhya Pradesh"),
    ("maharashtra", "Maharashtra"),
    ("manipur", "Manipur"),
    ("meghalaya", "Meghalaya"),
    ("mizoram", "Mizoram"),
    ("nagaland", "Nagaland"),
    ("odisha", "Odisha"),
    ("punjab", "Punjab"),
    ("rajasthan", "Rajasthan"),
    ("sikkim", "Sikkim"),
    ("tamil_nadu", "Tamil Nadu"),
    ("telangana", "Telangana"),
    ("tripura", "Tripura"),
    ("uttar_pradesh", "Uttar Pradesh"),
    ("uttarakhand", "Uttarakhand"),
    ("west_bengal", "West Bengal"),
    ("andaman_nicobar", "Andaman and Nicobar Islands"),
    ("chandigarh", "Chandigarh"),
    ("dadra_nagar_haveli_daman_diu", "Dadra and Nagar Haveli and Daman and Diu"),
    ("delhi", "Delhi"),
    ("jammu_kashmir", "Jammu and Kashmir"),
    ("ladakh", "Ladakh"),
    ("lakshadweep", "Lakshadweep"),
    ("puducherry", "Puducherry"),
    ("outside_india", "Outside India"),
]

#: Main cities for the states GRRAS draws from; every state also offers
#: "Other", so no answer to the state question leaves the city unanswerable.
CITIES = {
    "rajasthan": [
        ("jaipur", "Jaipur"),
        ("ajmer", "Ajmer"),
        ("kota", "Kota"),
        ("udaipur", "Udaipur"),
        ("jodhpur", "Jodhpur"),
        ("bikaner", "Bikaner"),
        ("alwar", "Alwar"),
        ("bhilwara", "Bhilwara"),
        ("sikar", "Sikar"),
        ("tonk", "Tonk"),
    ],
    "maharashtra": [
        ("pune", "Pune"),
        ("mumbai", "Mumbai"),
        ("nagpur", "Nagpur"),
        ("nashik", "Nashik"),
        ("chhatrapati_sambhajinagar", "Chhatrapati Sambhajinagar"),
    ],
    "delhi": [("new_delhi", "New Delhi")],
    "gujarat": [
        ("ahmedabad", "Ahmedabad"),
        ("surat", "Surat"),
        ("vadodara", "Vadodara"),
        ("rajkot", "Rajkot"),
    ],
    "madhya_pradesh": [
        ("indore", "Indore"),
        ("bhopal", "Bhopal"),
        ("gwalior", "Gwalior"),
        ("jabalpur", "Jabalpur"),
    ],
    "uttar_pradesh": [
        ("lucknow", "Lucknow"),
        ("noida", "Noida"),
        ("ghaziabad", "Ghaziabad"),
        ("kanpur", "Kanpur"),
        ("agra", "Agra"),
        ("varanasi", "Varanasi"),
    ],
    "haryana": [("gurugram", "Gurugram"), ("faridabad", "Faridabad")],
    "punjab": [("ludhiana", "Ludhiana"), ("amritsar", "Amritsar"), ("jalandhar", "Jalandhar")],
    "karnataka": [("bengaluru", "Bengaluru"), ("mysuru", "Mysuru")],
    "telangana": [("hyderabad", "Hyderabad")],
    "tamil_nadu": [("chennai", "Chennai"), ("coimbatore", "Coimbatore")],
    "west_bengal": [("kolkata", "Kolkata")],
    "bihar": [("patna", "Patna")],
    "chandigarh": [("chandigarh", "Chandigarh")],
}

COURSES = [
    ("python", "Python"),
    ("data_analytics", "Data Analytics"),
    ("data_science", "Data Science"),
    ("cyber_security", "Cyber Security"),
    ("full_stack", "Full Stack Development"),
    ("devops", "DevOps"),
    ("aws", "AWS Cloud"),
    ("ui_ux", "UI/UX Design"),
    ("red_hat", "Red Hat Linux"),
    ("salesforce", "Salesforce"),
    OTHER,
]

TRACKS = {
    "python": [("core_python", "Core Python"), ("python_django", "Python with Django")],
    "data_analytics": [
        ("excel_power_bi", "Excel and Power BI"),
        ("sql_tableau", "SQL and Tableau"),
    ],
    "data_science": [("machine_learning", "Machine Learning"), ("generative_ai", "Generative AI")],
    "cyber_security": [
        ("ethical_hacking", "Ethical Hacking"),
        ("ceh", "CEH certification"),
        ("network_security", "Network Security"),
    ],
    "full_stack": [
        ("mern", "MERN"),
        ("java_full_stack", "Java Full Stack"),
        ("python_full_stack", "Python Full Stack"),
    ],
    "devops": [("devops_aws", "DevOps with AWS"), ("devops_azure", "DevOps with Azure")],
    "aws": [
        ("solutions_architect", "Solutions Architect Associate"),
        ("developer_associate", "Developer Associate"),
        ("sysops", "SysOps Administrator"),
    ],
    "ui_ux": [("ui_ux_foundation", "UI/UX Foundation"), ("figma_advanced", "Advanced Figma")],
    "red_hat": [("rhcsa", "RHCSA"), ("rhce", "RHCE"), ("openshift", "OpenShift")],
    "salesforce": [("admin", "Salesforce Admin"), ("developer", "Salesforce Developer")],
}

ENQUIRY_FIELDS = [
    _field("contact_heading", "Contact details", "heading", group="Contact"),
    _field(
        "full_name",
        "Full name",
        "text",
        required=True,
        validation={"max_length": 120},
        group="Contact",
    ),
    _field(
        "mobile",
        "Mobile number",
        "phone",
        required=True,
        group="Contact",
        help_="10-digit mobile number, or with the country code (+91…).",
    ),
    _field("whatsapp_same", "WhatsApp on the same number", "boolean", group="Contact"),
    _field(
        "whatsapp_number",
        "WhatsApp number",
        "phone",
        group="Contact",
        show_if={"field": "whatsapp_same", "op": "ne", "value": True},
    ),
    _field("email", "Email", "email", group="Contact"),
    _field("location_heading", "Location", "heading", group="Location"),
    _select("state", "State", STATES, required=True, group="Location"),
    _field(
        "city",
        "City",
        "dependent_select",
        required=True,
        group="Location",
        options={
            "parent": "state",
            "choices": {
                value: _choices([*CITIES.get(value, []), OTHER]) for value, _label in STATES
            },
        },
    ),
    _field("course_heading", "Course interest", "heading", group="Course"),
    _select("course", "Course", COURSES, required=True, group="Course"),
    _field(
        "track",
        "Track",
        "dependent_select",
        group="Course",
        options={
            "parent": "course",
            "choices": {value: _choices(TRACKS.get(value, [OTHER])) for value, _label in COURSES},
        },
    ),
    _select(
        "preferred_centre",
        "Preferred centre",
        [("jaipur", "Jaipur"), ("pune", "Pune"), ("online", "Online only")],
        required=True,
        group="Course",
    ),
    _select(
        "mode",
        "Mode of study",
        [("classroom", "Classroom"), ("online", "Online"), ("hybrid", "Hybrid")],
        type_="radio",
        group="Course",
    ),
    _select(
        "batch_timing",
        "Preferred batch timing",
        [
            ("morning", "Morning"),
            ("afternoon", "Afternoon"),
            ("evening", "Evening"),
            ("weekend", "Weekend"),
        ],
        group="Course",
    ),
    _field("background_heading", "Background", "heading", group="Background"),
    _select(
        "qualification",
        "Highest qualification",
        [
            ("10th", "10th"),
            ("12th", "12th"),
            ("diploma", "Diploma"),
            ("graduate", "Graduate (B.Tech, BCA, B.Sc, B.Com…)"),
            ("postgraduate", "Postgraduate"),
            ("working_professional", "Working professional"),
        ],
        group="Background",
    ),
    _field(
        "passing_year",
        "Year of passing",
        "number",
        validation={"min": 1980, "max": 2035},
        group="Background",
        show_if={"field": "qualification", "op": "ne", "value": "working_professional"},
    ),
    _field(
        "company",
        "Current company",
        "text",
        validation={"max_length": 150},
        group="Background",
        show_if={"field": "qualification", "op": "eq", "value": "working_professional"},
    ),
    _select(
        "source",
        "How did they hear about GRRAS?",
        [
            ("walk_in", "Walk-in"),
            ("phone_call", "Phone call"),
            ("website", "Website"),
            ("google", "Google search or ads"),
            ("facebook_instagram", "Facebook or Instagram"),
            ("linkedin", "LinkedIn"),
            ("whatsapp", "WhatsApp"),
            ("referral", "Referral"),
            ("college_seminar", "College seminar"),
            OTHER,
        ],
        required=True,
        group="Background",
    ),
    _field(
        "referred_by",
        "Referred by",
        "text",
        validation={"max_length": 120},
        group="Background",
        show_if={"field": "source", "op": "eq", "value": "referral"},
    ),
    _field("utm_source", "UTM source", "hidden"),
    _field("utm_medium", "UTM medium", "hidden"),
    _field("utm_campaign", "UTM campaign", "hidden"),
    _field("remarks", "Remarks", "textarea", validation={"max_length": 2000}),
    _field(
        "consent",
        "The enquirer agrees to be contacted by GRRAS by phone, WhatsApp, SMS and email "
        "about courses and admissions.",
        "consent",
        required=True,
    ),
]

_NOT_REACHED = ["not_answered", "busy", "switched_off", "call_back_later"]

FOLLOW_UP_FIELDS = [
    _select(
        "call_status",
        "Call outcome",
        [
            ("connected", "Connected"),
            ("not_answered", "Not answered"),
            ("busy", "Busy"),
            ("switched_off", "Switched off"),
            ("wrong_number", "Wrong number"),
            ("call_back_later", "Asked to call back later"),
        ],
        required=True,
    ),
    _select(
        "lead_stage",
        "Lead stage",
        [
            ("interested", "Interested"),
            ("counselling_booked", "Counselling booked"),
            ("demo_booked", "Demo class booked"),
            ("registered", "Registered"),
            ("not_interested", "Not interested"),
            ("not_eligible", "Not eligible"),
        ],
        required=True,
        show_if={"field": "call_status", "op": "eq", "value": "connected"},
    ),
    _select(
        "lost_reason",
        "Why not?",
        [
            ("fees", "Fees too high"),
            ("competitor", "Chose another institute"),
            ("timing", "Batch timing does not suit"),
            ("online_preference", "Wants online only"),
            ("location", "Centre too far"),
            ("went_silent", "Stopped responding"),
            ("chose_nothing", "Decided not to study now"),
            OTHER,
        ],
        required=True,
        show_if={"field": "lead_stage", "op": "eq", "value": "not_interested"},
    ),
    _field(
        "competitor",
        "Which institute?",
        "text",
        validation={"max_length": 120},
        show_if={"field": "lost_reason", "op": "eq", "value": "competitor"},
    ),
    _field(
        "demo_at",
        "Demo class date and time",
        "datetime",
        required=True,
        validation={"not_past": True},
        show_if={"field": "lead_stage", "op": "eq", "value": "demo_booked"},
    ),
    _field(
        "next_follow_up",
        "Next follow-up",
        "datetime",
        required=True,
        validation={"not_past": True},
        show_if={"field": "call_status", "op": "in", "value": _NOT_REACHED},
    ),
    _field(
        "lead_quality",
        "Lead quality",
        "rating",
        validation={"max": 5},
        show_if={"field": "call_status", "op": "eq", "value": "connected"},
        help_="1 = cold, 5 = ready to join.",
    ),
    _field("notes", "Notes", "textarea", validation={"max_length": 4000}),
]

FORMS = [
    {"slug": "enquiry", "name": "Enquiry", "entity": "enquiry", "fields": ENQUIRY_FIELDS},
    {
        "slug": "enquiry-follow-up",
        "name": "Enquiry follow-up",
        "entity": "enquiry",
        "fields": FOLLOW_UP_FIELDS,
    },
]


def _schema_hash(fields: list[dict]) -> str:
    """The same recipe as `services._schema_hash` at the time of writing:
    fields in order, ``show_if`` appended only when a field has one."""
    ordered = [
        (f["key"], f["type"], f["required"], f["options"], f["validation"])
        + ((f["show_if"],) if f["show_if"] else ())
        for f in fields
    ]
    payload = json.dumps(ordered, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seed_forms(apps, schema_editor):
    FormDefinition = apps.get_model("forms", "FormDefinition")
    FormVersion = apps.get_model("forms", "FormVersion")
    FormField = apps.get_model("forms", "FormField")

    for spec in FORMS:
        definition, _created = FormDefinition.objects.get_or_create(
            slug=spec["slug"],
            defaults={"name": spec["name"], "entity": spec["entity"]},
        )
        if FormVersion.objects.filter(definition=definition).exists():
            # Already seeded, or an administrator made one by hand: leave it.
            continue
        version = FormVersion.objects.create(
            definition=definition,
            number=1,
            status="published",
            schema_hash=_schema_hash(spec["fields"]),
            published_at=timezone.now(),
        )
        FormField.objects.bulk_create(
            [
                FormField(
                    version=version,
                    key=field["key"],
                    label=field["label"],
                    help=field["help"],
                    type=field["type"],
                    required=field["required"],
                    order=index,
                    group=field["group"],
                    options=field["options"],
                    validation=field["validation"],
                    show_if=field["show_if"],
                )
                for index, field in enumerate(spec["fields"])
            ]
        )


def unseed_forms(apps, schema_editor):
    FormDefinition = apps.get_model("forms", "FormDefinition")
    FormResponse = apps.get_model("forms", "FormResponse")
    FormAssignment = apps.get_model("forms", "FormAssignment")
    for spec in FORMS:
        definition = FormDefinition.objects.filter(slug=spec["slug"]).first()
        if definition is None:
            continue
        answered = FormResponse.objects.filter(version__definition=definition).exists()
        sent = FormAssignment.objects.filter(definition=definition).exists()
        if not answered and not sent:
            definition.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("forms", "0003_assignments_uploads_meritto_fields"),
    ]

    operations = [
        migrations.RunPython(seed_forms, unseed_forms),
    ]
