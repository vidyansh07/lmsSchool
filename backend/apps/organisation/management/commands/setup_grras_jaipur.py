"""Set this installation up for GRRAS Jaipur: two offices and a placement role.

GRRAS Solutions runs two places in Jaipur — the corporate office and the one at
Himmat Nagar. Everything else in this product is written for an institution with
any number of centres, and that stays true; this command only fills in the two
that exist, so an operator does not have to type them in and get the codes
slightly wrong.

Idempotent on purpose. It is run on a fresh database, on staging, and again
after a restore, and it must leave the same two rows each time rather than a
third office named "GRRAS corporate ".

Why the corporate office keeps the ``MAIN`` code
------------------------------------------------
The first migration created a centre coded ``MAIN``, and every existing student,
batch, enrolment and payment points at it. Renaming the *code* would orphan
nothing — the rows are joined by id — but ``apps.work.services`` reads
``code="MAIN"`` when it needs a centre to fall back on, and three seeds name it.
So this renames what people read (the name and the city) and leaves the code
where the code is already depended on. The office displays as
"MAIN — GRRAS Corporate", which is the right name in every picker.

Himmat Nagar is new, so it gets the code it should have had from the start.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.authorization.models import Role
from apps.authorization.services import create_role
from apps.organisation.models import Branch

#: The corporate office. Keeps ``MAIN`` for the reason in the module docstring.
CORPORATE = {"code": "MAIN", "name": "GRRAS Corporate", "city": "Jaipur"}

#: The second office.
HIMMAT_NAGAR = {"code": "HIMMAT", "name": "GRRAS Himmat Nagar", "city": "Jaipur"}

#: The placement officer, as a role an administrator can edit rather than one
#: welded into the code.
#:
#: GRRAS places students and advertises the hiring partners it places them
#: with, but there was no role for the person who does it: placement work was
#: being done from a counsellor or an administrator account. Built from the
#: counsellor kind because the work is the same shape — people, follow-ups and
#: calls — and narrowed from there.
#:
#: It is a `Role` row, not a new member of `UserRole`, so the administrator can
#: add and remove a permission as the job changes without a deployment. That is
#: also why the permission list is the floor and not the ceiling.
PLACEMENT_OFFICER: dict[str, Any] = {
    "slug": "placement-officer",
    "name": "Placement officer",
    "description": (
        "Runs placement: hiring partners, interview calls, mock interviews and "
        "resume reviews. Sees students, batches and enrolments, and no fees."
    ),
    "kind": UserRole.COUNSELLOR,
    "permissions": [
        {"code": "student.view_any"},
        {"code": "student.update_any"},
        {"code": "batch.view_any"},
        {"code": "enrolment.view_any"},
        {"code": "activity.view_any"},
        {"code": "activity.create"},
        {"code": "activity.complete"},
        {"code": "communication.send"},
        {"code": "communication.view_any"},
        {"code": "report.view_any"},
    ],
}


class Command(BaseCommand):
    help = "Create the two GRRAS Jaipur offices and the placement officer role."

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            made, changed = self._offices()
            role = self._placement_role()

        for line in made:
            self.stdout.write(self.style.SUCCESS(f"created  {line}"))
        for line in changed:
            self.stdout.write(f"updated  {line}")
        self.stdout.write(role)

    def _offices(self) -> tuple[list[str], list[str]]:
        made: list[str] = []
        changed: list[str] = []
        for office in (CORPORATE, HIMMAT_NAGAR):
            branch, created = Branch.objects.get_or_create(
                code=office["code"],
                defaults={"name": office["name"], "city": office["city"], "is_active": True},
            )
            if created:
                made.append(str(branch))
                continue
            # An office that exists is corrected rather than duplicated, which
            # is what makes a second run safe. An office somebody deactivated on
            # purpose is left deactivated: that is an operational decision, not
            # a typo for this command to undo.
            fields = []
            if branch.name != office["name"]:
                branch.name = office["name"]
                fields.append("name")
            if branch.city != office["city"]:
                branch.city = office["city"]
                fields.append("city")
            if fields:
                branch.save(update_fields=[*fields, "updated_at"])
                changed.append(f"{branch} ({', '.join(fields)})")
        return made, changed

    def _placement_role(self) -> str:
        # `Role.all_objects` rather than `Role.objects`: a role somebody put in
        # the recycle bin still holds the slug, and creating a twin of it on the
        # next run is worse than leaving the binned one alone.
        existing = Role.all_objects.filter(slug=PLACEMENT_OFFICER["slug"]).first()
        if existing is not None:
            return f"present  role {existing.name}"
        actor = User.objects.filter(role=UserRole.SUPERADMIN, is_active=True).order_by("pk").first()
        if actor is None:
            # Roles are created by somebody, and the audit trail records who.
            # With no administrator yet there is nobody to attribute it to, so
            # this says so rather than inventing an actor.
            return self.style.WARNING(
                "skipped  role Placement officer — no superadmin to attribute it to; "
                "run this again once an administrator exists"
            )
        role = create_role(
            actor=actor,
            slug=PLACEMENT_OFFICER["slug"],
            name=PLACEMENT_OFFICER["name"],
            kind=PLACEMENT_OFFICER["kind"],
            description=PLACEMENT_OFFICER["description"],
            permissions=PLACEMENT_OFFICER["permissions"],
        )
        return self.style.SUCCESS(f"created  role {role.name}")
