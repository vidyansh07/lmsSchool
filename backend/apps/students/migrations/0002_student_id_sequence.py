"""Create the PostgreSQL sequence backing human-readable student IDs.

A sequence rather than ``MAX(id) + 1``: sequence allocation is atomic and does
not block, so two concurrent admissions can never be handed the same number.
Gaps left by rolled-back transactions are expected and harmless.
"""

from django.db import migrations

SEQUENCE = "student_public_id_seq"


class Migration(migrations.Migration):
    dependencies = [("students", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
