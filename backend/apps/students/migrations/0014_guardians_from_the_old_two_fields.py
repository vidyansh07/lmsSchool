"""Give every student who already had a guardian a guardian row.

`guardian_name` and `guardian_phone` have held one guardian since the
beginning. `Guardian` holds as many as a family has, with a relation and an
email, which is what the messaging settings' "first guardian / all guardians"
choice needs.

This copies, it does not move: the two columns keep their values. A thousand
real answers are not worth discarding to make a diagram tidy, and a student
record that lost its only guardian's name because a migration was confident
would be the worst kind of data loss — silent, and about somebody's parent.

Idempotent: a student who already has a guardian row is left alone, so a
re-run (or a database restored from a dump that has already been through
this) does not produce twins.
"""

from __future__ import annotations

from django.db import migrations


def copy_guardians(apps, schema_editor):
    StudentProfile = apps.get_model("students", "StudentProfile")
    Guardian = apps.get_model("students", "Guardian")

    with_guardian = StudentProfile.objects.exclude(guardian_name="").only(
        "id", "guardian_name", "guardian_phone"
    )
    already = set(Guardian.objects.values_list("student_id", flat=True))
    Guardian.objects.bulk_create(
        [
            Guardian(
                student_id=profile.id,
                name=profile.guardian_name.strip(),
                # The old pair never said who the person was, and guessing
                # "father" from a name is exactly the sort of inference that
                # looks tidy and is wrong for half the rows.
                relation="guardian",
                mobile=(profile.guardian_phone or "").strip(),
                email="",
                occupation="",
                is_primary=True,
            )
            for profile in with_guardian
            if profile.id not in already and profile.guardian_name.strip()
        ],
        batch_size=500,
    )


def drop_copies(apps, schema_editor):
    """Only the rows this migration could have made: one primary guardian
    whose name matches the column it came from, with nothing else filled in."""
    Guardian = apps.get_model("students", "Guardian")
    for row in Guardian.objects.filter(
        is_primary=True, relation="guardian", email="", occupation=""
    ).select_related("student"):
        if row.name == (row.student.guardian_name or "").strip():
            row.delete()


class Migration(migrations.Migration):
    dependencies = [("students", "0013_guardian")]

    operations = [migrations.RunPython(copy_guardians, drop_copies)]
