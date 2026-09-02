"""Sequences for batch and enrolment codes.

Same reasoning as the student, trainer and course sequences: allocation is
atomic, so two concurrent creations can never receive the same code.

Both sequences are created here rather than one per app, because the enrolment
app's initial migration depends on batches and splitting them would add a
dependency edge for no benefit.
"""

from django.db import migrations

SEQUENCES = ("batch_public_code_seq", "enrolment_public_code_seq")


class Migration(migrations.Migration):
    dependencies = [("batches", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=";\n".join(
                f"CREATE SEQUENCE IF NOT EXISTS {name} START WITH 1 INCREMENT BY 1"
                for name in SEQUENCES
            )
            + ";",
            reverse_sql=";\n".join(f"DROP SEQUENCE IF EXISTS {name}" for name in SEQUENCES) + ";",
        ),
    ]
