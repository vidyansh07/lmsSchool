"""Hold an interview's result back until somebody releases it.

The three interview types in the seeded catalogue — `mock-interview`,
`technical-interview` and `hr-interview` — are all `visible_to_student=True`,
and `create_activity` resolves an instance's `student_visible` from the type.
So a trainer who scored a mock interview published that score, and the
paragraph they wrote about how the student came across, the instant they
saved it. The first draft, typed while the student was still in the room, was
the thing the student read.

The owner's decision (26 October 2026) is that a result is written privately
and published deliberately. `ActivityType.release_required` is that gate, and
this turns it on for the three types it was built for.

Only those three. `resume-review`, `code-review` and `project-review` are
also visible to students and also carry a score, and whether they should be
held back the same way is a question for the owner rather than an inference
from this one — so they are left exactly as they are.

Existing interviews are not touched. An activity already published has been
read; hiding it now would tell the student something was taken away, which is
a worse outcome than the inconsistency. Only interviews created after this
point start held back.
"""

from __future__ import annotations

from django.db import migrations

#: The seeded catalogue's own slugs, matched exactly — a type an
#: administrator added by hand is theirs to configure.
HELD_BACK = ("mock-interview", "technical-interview", "hr-interview")


def hold_results_back(apps, schema_editor):
    ActivityType = apps.get_model("work", "ActivityType")
    ActivityType.objects.filter(slug__in=HELD_BACK, visible_to_student=True).update(
        release_required=True
    )


def publish_on_save_again(apps, schema_editor):
    ActivityType = apps.get_model("work", "ActivityType")
    ActivityType.objects.filter(slug__in=HELD_BACK).update(release_required=False)


class Migration(migrations.Migration):
    dependencies = [("work", "0010_activitytype_release_required")]

    operations = [migrations.RunPython(hold_results_back, publish_on_save_again)]
