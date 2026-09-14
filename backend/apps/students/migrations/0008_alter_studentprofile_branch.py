"""Make the centre compulsory, now that every row carries one.

Split from the ``AddField`` in 0003_studentprofile_branch because a single non-null
``AddField`` cannot apply to a populated table, and split from the backfill in
``organisation.0002_default_branch`` because the backfill has to have run first.
A nullable branch here would be worse than no branch at all: under the
fail-closed rule in :mod:`apps.organisation.scoping` it would be a record that
every branch-scoped manager is hidden from, with nobody able to say why.

``accounts.User`` deliberately has no migration of this kind — see that field's
help text.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0007_studentprofile_branch"),
        ("organisation", "0002_default_branch"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentprofile",
            name="branch",
            field=models.ForeignKey(
                help_text="The centre this student was admitted to. A later transfer may put their class at another one; this is where their record is kept.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="students",
                to="organisation.branch",
                verbose_name="branch",
            ),
        ),
    ]
