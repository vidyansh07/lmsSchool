"""Create the PostgreSQL sequence backing human-readable assignment codes.

Same shape as the student, trainer, course, batch and enrolment sequences:
atomic allocation, so two trainers creating work at once cannot be handed the
same code.
"""

from django.db import migrations

SEQUENCE = "assignment_public_code_seq"


class Migration(migrations.Migration):
    dependencies = [("assignments", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
