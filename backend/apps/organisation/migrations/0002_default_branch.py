"""Give every existing person and class a centre.

Written as a data migration rather than a column default because the default has
to be a real row, and a row cannot be created by a column default. One branch is
created — the institution as it exists today — and everything is stamped with
it; an operator renames it and adds the second centre afterwards.

Superadmins are deliberately left unstamped. ``NULL`` on a superadmin is what
"every centre" means, and stamping them would silently narrow the one account
that has to be able to find a mis-filed record anywhere. The role is compared as
a bare string rather than through :class:`~apps.accounts.roles.UserRole`,
because a data migration that imports application code breaks the first time
that code changes.

The reverse is blunt, on purpose
--------------------------------
``unstamp`` clears the branch column on *every* row of the four tables, not only
the rows ``stamp`` wrote. On the scratch database ``scripts/check_migrations.sh``
exercises that is correct and total. On a real database that has since gained a
second centre it would be destructive — which is the ordinary property of
reversing a backfill, and worth knowing before anybody runs it there.
"""

from django.db import migrations

DEFAULT_CODE = "MAIN"
DEFAULT_NAME = "Main centre"

#: The four tables that carry a branch. ``accounts.User`` is handled separately
#: below because its rule has an exception; the reverse treats all four alike.
STAMPED = (
    ("batches", "Batch"),
    ("students", "StudentProfile"),
    ("trainers", "TrainerProfile"),
)


def stamp(apps, schema_editor):
    Branch = apps.get_model("organisation", "Branch")
    # `get_or_create` runs inside the migration transaction, so it cannot race a
    # second worker. Do not "improve" it into a plain `create()`.
    branch, _created = Branch.objects.get_or_create(
        code=DEFAULT_CODE, defaults={"name": DEFAULT_NAME, "is_active": True}
    )

    for label, model_name in STAMPED:
        apps.get_model(label, model_name).objects.filter(branch__isnull=True).update(branch=branch)

    User = apps.get_model("accounts", "User")
    User.objects.filter(branch__isnull=True).exclude(role="superadmin").update(branch=branch)


def unstamp(apps, schema_editor):
    for label, model_name in (*STAMPED, ("accounts", "User")):
        apps.get_model(label, model_name).objects.update(branch=None)
    apps.get_model("organisation", "Branch").objects.filter(code=DEFAULT_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organisation", "0001_initial"),
        ("accounts", "0005_user_branch"),
        ("batches", "0006_batch_branch"),
        ("students", "0007_studentprofile_branch"),
        ("trainers", "0003_trainerprofile_branch"),
    ]

    operations = [migrations.RunPython(stamp, unstamp)]
