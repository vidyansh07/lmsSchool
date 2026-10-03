"""Seed the empty "Class report: extra questions" form.

Every class report asks this form's questions after its own. It starts with
none, so nothing changes until an administrator adds questions in the form
builder and publishes version 2. Version 1 is published empty so the form
is visible, and editable, in the builder from the start.
"""

from __future__ import annotations

import hashlib
import json

from django.db import migrations
from django.utils import timezone

SLUG = "dsr-extra"


def seed(apps, schema_editor):
    FormDefinition = apps.get_model("forms", "FormDefinition")
    FormVersion = apps.get_model("forms", "FormVersion")
    definition, _created = FormDefinition.objects.get_or_create(
        slug=SLUG, defaults={"name": "Class report: extra questions", "entity": "dsr"}
    )
    if FormVersion.objects.filter(definition=definition).exists():
        return
    FormVersion.objects.create(
        definition=definition,
        number=1,
        status="published",
        schema_hash=hashlib.sha256(json.dumps([]).encode("utf-8")).hexdigest(),
        published_at=timezone.now(),
    )


def unseed(apps, schema_editor):
    FormDefinition = apps.get_model("forms", "FormDefinition")
    FormField = apps.get_model("forms", "FormField")
    definition = FormDefinition.objects.filter(slug=SLUG).first()
    if definition is not None and not FormField.objects.filter(
        version__definition=definition
    ).exists():
        definition.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("forms", "0006_alter_formdefinition_entity"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
