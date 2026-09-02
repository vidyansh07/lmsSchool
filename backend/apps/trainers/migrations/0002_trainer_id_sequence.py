"""Create the PostgreSQL sequence backing human-readable trainer IDs."""

from django.db import migrations

SEQUENCE = "trainer_public_id_seq"


class Migration(migrations.Migration):
    dependencies = [("trainers", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
