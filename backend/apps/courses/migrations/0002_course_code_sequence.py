"""Create the PostgreSQL sequence backing human-readable course codes.

Matches the student and trainer identifier sequences: atomic allocation, so two
concurrent course creations can never receive the same code.
"""

from django.db import migrations

SEQUENCE = "course_public_code_seq"


class Migration(migrations.Migration):
    dependencies = [("courses", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
