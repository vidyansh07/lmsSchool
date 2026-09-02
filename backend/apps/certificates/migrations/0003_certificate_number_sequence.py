"""Create the PostgreSQL sequence backing certificate numbers.

Atomic allocation, so two administrators issuing at the same moment cannot be
handed the same number — which for a certificate is not a cosmetic problem.
"""

from django.db import migrations

SEQUENCE = "certificate_number_seq"


class Migration(migrations.Migration):
    dependencies = [("certificates", "0002_initial")]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
    ]
