"""The academic year every existing admission already belonged to.

A year is a record, not a number read off a date (see `AcademicYear`), so one
has to exist before anything can be filed under it. This creates the current
calendar year, marks it current, and stops: naming past years the institute
may or may not have run is not this migration's guess to make, and an
administrator adds the ones they need on the Academic Year screen.

Idempotent, and it never changes a year that already exists — including which
one is current, which may well have been set deliberately.
"""

from __future__ import annotations

from datetime import date

from django.db import migrations


def seed_current_year(apps, schema_editor):
    AcademicYear = apps.get_model("organisation", "AcademicYear")
    if AcademicYear.objects.exists():
        return
    year = date.today().year
    AcademicYear.objects.create(
        name=str(year),
        starts_on=date(year, 1, 1),
        ends_on=date(year, 12, 31),
        is_current=True,
    )


def unseed(apps, schema_editor):
    AcademicYear = apps.get_model("organisation", "AcademicYear")
    AcademicYear.objects.filter(name=str(date.today().year)).delete()


class Migration(migrations.Migration):
    dependencies = [("organisation", "0004_academicyear_bank")]

    operations = [migrations.RunPython(seed_current_year, unseed)]
