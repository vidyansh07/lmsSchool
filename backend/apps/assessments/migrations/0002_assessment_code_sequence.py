"""Create the PostgreSQL sequence backing human-readable assessment codes."""

from django.db import migrations

SEQUENCE = "assessment_public_code_seq"


class Migration(migrations.Migration):
    dependencies = [("assessments", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
