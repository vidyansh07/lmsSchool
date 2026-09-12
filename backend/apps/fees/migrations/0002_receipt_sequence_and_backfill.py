"""Receipt numbers, and the fees that were already agreed.

Before the ledger, a student carried one ``fee_amount``. Where that student
has exactly one enrolment the number can only have meant that course, so it
becomes the enrolment's fee plan. A student on several courses is left for a
counsellor to set by hand — guessing which course a number belonged to would
put a wrong figure on a receipt.
"""

from django.db import migrations

SEQUENCE = "fee_receipt_number_seq"


def backfill_plans(apps, schema_editor):
    StudentProfile = apps.get_model("students", "StudentProfile")
    Enrollment = apps.get_model("enrollments", "Enrollment")
    FeePlan = apps.get_model("fees", "FeePlan")
    for student in StudentProfile.objects.filter(fee_amount__isnull=False).iterator():
        enrollments = list(
            Enrollment.objects.filter(student=student, deleted_at__isnull=True).order_by("enrolled_at")
        )
        if len(enrollments) != 1:
            continue
        enrollment = enrollments[0]
        if FeePlan.objects.filter(enrollment=enrollment).exists():
            continue
        FeePlan.objects.create(
            enrollment=enrollment,
            agreed_amount=student.fee_amount,
            created_by_id=student.fee_amount_updated_by_id,
            updated_by_id=student.fee_amount_updated_by_id,
            notes="Carried over from the fee recorded at registration.",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("fees", "0001_fee_plan_and_payments"),
        ("students", "0006_roll_number"),
        ("enrollments", "0004_enrollment_is_upgrade_enrollment_transferred_to_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE} START WITH 1 INCREMENT BY 1;",
            reverse_sql=f"DROP SEQUENCE IF EXISTS {SEQUENCE};",
        ),
        migrations.RunPython(backfill_plans, migrations.RunPython.noop),
    ]
