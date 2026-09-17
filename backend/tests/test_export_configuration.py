"""`manage.py export_configuration` (Phase 23, `docs/erp/BACKUP_AND_RECOVERY.md`).

It produces one JSON document with all seven configuration categories, never
writes anything, and does not error when any of them is an empty table.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.authorization.models import Permission, Role
from apps.communication.models import MessageTemplate
from apps.forms.models import FormDefinition
from apps.work.models import ActivityType

CATEGORIES = (
    "roles",
    "permissions",
    "policies",
    "forms",
    "activity_types",
    "automation_rules",
    "message_templates",
)


def run() -> dict:
    out = StringIO()
    call_command("export_configuration", stdout=out)
    return json.loads(out.getvalue())


@pytest.mark.django_db
def test_export_is_valid_json_with_every_category():
    document = run()

    assert set(CATEGORIES) <= document.keys()
    assert "generated_at" in document
    for category in CATEGORIES:
        assert isinstance(document[category], list), category


@pytest.mark.django_db
def test_export_includes_the_seeded_catalog_rows():
    """Every category here is seeded by a data migration (system roles, the
    permission catalog, the form catalog, the activity types, the automation
    rules, the starter email templates) — exactly what a fresh install has
    configured. The export must actually contain them, not just an empty
    shell with the right keys."""
    document = run()

    assert Role.objects.count() > 0
    assert len(document["roles"]) == Role.objects.count()
    assert Permission.objects.count() > 0
    assert len(document["permissions"]) == Permission.objects.count()
    assert len(document["forms"]) > 0
    assert len(document["activity_types"]) > 0
    assert len(document["automation_rules"]) > 0
    assert len(document["message_templates"]) > 0
    # Every configured policy schema key, resolved to its current or default
    # value — never empty, since a key nobody has touched still has a default.
    assert len(document["policies"]) > 0


@pytest.mark.django_db
def test_export_handles_an_empty_table_for_forms_and_templates():
    """No category in this codebase's fixed catalog is actually empty on a
    fresh install, so the empty-table path is exercised explicitly: hard-
    delete every row of two of them and confirm the export still returns a
    valid (empty) list for each rather than erroring. Every seeded activity
    type `PROTECT`s the form it points at, so those references are cleared
    first — the same thing a real deletion of a form would require."""
    ActivityType.all_objects.update(form=None)
    FormDefinition.all_objects.all().delete()
    MessageTemplate.all_objects.all().delete()

    document = run()

    assert document["forms"] == []
    assert document["message_templates"] == []


@pytest.mark.django_db
def test_export_does_not_write_to_the_database():
    role_count_before = Role.objects.count()
    permission_count_before = Permission.objects.count()

    run()

    assert Role.objects.count() == role_count_before
    assert Permission.objects.count() == permission_count_before
