"""Name the payment methods properly, and seed the lists the desk picks from.

Two jobs, both idempotent:

1. `card` and `bank_transfer` were this enum's original, vaguer names. The
   fourteen methods the counter actually uses name them `swipe_card` and
   `net_banking`, so the rows carrying the old values are moved across. This
   changes what a payment is *called*, never what it was worth: no amount,
   date, receipt number or plan is touched.
2. One payment category ("Fees") and one tax group ("GST"), each marked
   default, because the payment dialog opens with them and a fresh install
   should not present an empty select on the first payment anybody takes.
"""

from __future__ import annotations

from django.db import migrations

RENAMES = (("card", "swipe_card"), ("bank_transfer", "net_banking"))


def rename_methods(apps, schema_editor):
    FeePayment = apps.get_model("fees", "FeePayment")
    for old, new in RENAMES:
        FeePayment.objects.filter(method=old).update(method=new)


def restore_methods(apps, schema_editor):
    FeePayment = apps.get_model("fees", "FeePayment")
    for old, new in RENAMES:
        FeePayment.objects.filter(method=new).update(method=old)


def seed_lists(apps, schema_editor):
    PaymentCategory = apps.get_model("fees", "PaymentCategory")
    TaxGroup = apps.get_model("fees", "TaxGroup")
    if not PaymentCategory.objects.exists():
        PaymentCategory.objects.create(name="Fees", is_default=True, is_active=True)
    if not TaxGroup.objects.exists():
        TaxGroup.objects.create(name="GST", is_default=True, is_active=True)


def unseed_lists(apps, schema_editor):
    """Only the seeded rows, and only while nothing points at them."""
    PaymentCategory = apps.get_model("fees", "PaymentCategory")
    TaxGroup = apps.get_model("fees", "TaxGroup")
    FeePayment = apps.get_model("fees", "FeePayment")
    for model, name, field in (
        (PaymentCategory, "Fees", "category"),
        (TaxGroup, "GST", "tax_group"),
    ):
        row = model.objects.filter(name=name).first()
        if row is not None and not FeePayment.objects.filter(**{field: row}).exists():
            row.delete()


class Migration(migrations.Migration):
    dependencies = [("fees", "0007_paymentcategory_taxgroup_feepayment_apply_tax_and_more")]

    operations = [
        migrations.RunPython(rename_methods, restore_methods),
        migrations.RunPython(seed_lists, unseed_lists),
    ]
