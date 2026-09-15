"""Seed the permission catalog from the enum and the six system roles from the
code matrix (ADR-01). Reversible: the reverse deletes only system rows that
nothing references."""

from django.db import migrations


def seed(apps, schema_editor):
    from apps.authorization.sync import sync_catalog

    sync_catalog(apps)


def unseed(apps, schema_editor):
    Role = apps.get_model("authorization", "Role")
    Permission = apps.get_model("authorization", "Permission")
    Role.objects.filter(is_system=True, users__isnull=True).delete()
    Permission.objects.filter(grants__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("authorization", "0001_initial"),
        ("accounts", "0006_roles_as_rows"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
