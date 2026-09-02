"""Create the PostgreSQL sequence backing human-readable project codes."""

from django.db import migrations

SEQUENCE = "project_public_code_seq"


class Migration(migrations.Migration):
    dependencies = [("projects", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
