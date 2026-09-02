"""Create the PostgreSQL sequence backing human-readable examination codes."""

from django.db import migrations

SEQUENCE = "exam_public_code_seq"


class Migration(migrations.Migration):
    dependencies = [("exams", "0002_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
