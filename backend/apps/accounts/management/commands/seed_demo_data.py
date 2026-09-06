"""Create fake demo accounts and profiles for local and staging environments.

Safety properties, in order of importance:

1. **Refuses to run in production.** Gated on ``settings.ALLOW_DEMO_SEED``,
   which is ``False`` everywhere except local, test, development and staging.
2. **No password in source control.** The password comes from
   ``DEMO_USER_PASSWORD``; without it the command exits with an error rather
   than inventing a guessable default, and it must pass the project's own
   password policy.
3. **Obviously fake data.** Every address is on ``@demo.grras.invalid`` — the
   ``.invalid`` TLD is reserved by RFC 2606 and can never be delivered to a real
   inbox — and every name is a placeholder. No real learner data is ever used.
4. **Idempotent.** Re-running updates the existing demo users and their profiles
   instead of creating duplicates, and never touches non-demo accounts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User, UserRole
from apps.common.identifiers import next_student_id, next_trainer_id
from apps.students.models import FeeStatus, Qualification, StudentProfile
from apps.trainers.models import TrainerProfile

DEMO_EMAIL_DOMAIN = "demo.grras.invalid"

FIRST_NAMES = [
    "Aarav",
    "Diya",
    "Vivaan",
    "Ananya",
    "Aditya",
    "Ishita",
    "Arjun",
    "Kavya",
    "Reyansh",
    "Meera",
    "Kabir",
    "Riya",
    "Advik",
    "Saanvi",
    "Ayaan",
    "Anika",
    "Vihaan",
    "Navya",
    "Rudra",
    "Aisha",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Meena",
    "Singh",
    "Jain",
    "Agarwal",
    "Yadav",
    "Rathore",
    "Choudhary",
]
CITIES = [
    ("Jaipur", "Rajasthan"),
    ("Jodhpur", "Rajasthan"),
    ("Udaipur", "Rajasthan"),
    ("Kota", "Rajasthan"),
    ("Ajmer", "Rajasthan"),
]
INSTITUTIONS = [
    "Demo Institute of Technology",
    "Sample Engineering College",
    "Placeholder University",
    "Example Polytechnic",
]
TRAINER_SPECIALITIES = [
    ("Senior Linux Trainer", ["Linux", "RHCSA", "Bash"], "Red Hat systems administration", 12),
    ("Python & Django Trainer", ["Python", "Django", "REST"], "Backend web development", 8),
    ("Cloud Trainer", ["AWS", "Docker", "Kubernetes"], "Cloud and container platforms", 6),
    ("Networking Trainer", ["CCNA", "Routing", "Switching"], "Enterprise networking", 15),
    ("Data Science Trainer", ["Python", "Pandas", "ML"], "Applied data science", 5),
]
FEE_CYCLE = [FeeStatus.PAID, FeeStatus.PARTIAL, FeeStatus.PENDING, FeeStatus.OVERDUE]
QUALIFICATION_CYCLE = [
    Qualification.BACHELORS,
    Qualification.HIGHER_SECONDARY,
    Qualification.DIPLOMA,
    Qualification.MASTERS,
]

ADMIN_COUNT = 2
TRAINER_COUNT = 5
STUDENT_COUNT = 20

#: Roles that may open the Django admin. A manager runs academic operations
#: through the LMS, not through the database editor, so they are not here.
STAFF_ROLES = frozenset({UserRole.SUPERADMIN, UserRole.ADMIN})


@dataclass
class DemoAccount:
    local_part: str
    first_name: str
    last_name: str
    role: str
    profile: dict[str, Any] = field(default_factory=dict)

    @property
    def email(self) -> str:
        return f"{self.local_part}@{DEMO_EMAIL_DOMAIN}"


def _person(index: int) -> tuple[str, str]:
    return FIRST_NAMES[index % len(FIRST_NAMES)], LAST_NAMES[index % len(LAST_NAMES)]


def build_demo_accounts() -> list[DemoAccount]:
    """Deterministic fake roster, so a re-run produces the same people."""
    accounts: list[DemoAccount] = [
        # Every role in the model gets a demo account. §15.5 asks for this by
        # name, and the reason is the one that keeps biting: a role nobody can
        # sign in as is a role nobody checks, and "the manager cannot do X" gets
        # discovered by a manager rather than by a reviewer.
        DemoAccount("superadmin", "Sonia", "Superson", UserRole.SUPERADMIN),
        DemoAccount("admin", "Ada", "Adminson", UserRole.ADMIN),
        DemoAccount("admin2", "Owen", "Operator", UserRole.ADMIN),
        DemoAccount("manager", "Maya", "Managerial", UserRole.MANAGER),
        DemoAccount("counsellor", "Chetan", "Counsell", UserRole.COUNSELLOR),
    ]

    for index, (title, skills, expertise, years) in enumerate(TRAINER_SPECIALITIES, start=1):
        first, last = _person(index + 3)
        accounts.append(
            DemoAccount(
                f"trainer{index}",
                first,
                last,
                UserRole.TRAINER,
                profile={
                    "professional_title": title,
                    "skills": skills,
                    "expertise": expertise,
                    "qualifications": "Demo certification (fake record)",
                    "years_of_experience": years,
                    "bio": f"Demo trainer profile for {title.lower()}. Not a real person.",
                    "professional_links": {"website": "https://example.invalid"},
                },
            )
        )

    for index in range(1, STUDENT_COUNT + 1):
        first, last = _person(index)
        city, state = CITIES[index % len(CITIES)]
        accounts.append(
            DemoAccount(
                f"student{index}",
                first,
                last,
                UserRole.STUDENT,
                profile={
                    "city": city,
                    "state": state,
                    "country": "India",
                    "address_line1": f"{index} Demo Street",
                    "postal_code": f"3020{index % 10:02d}",
                    "qualification": QUALIFICATION_CYCLE[index % len(QUALIFICATION_CYCLE)],
                    "institution": INSTITUTIONS[index % len(INSTITUTIONS)],
                    "graduation_year": 2018 + (index % 7),
                    "emergency_contact_name": f"{last} Family Contact",
                    "emergency_contact_phone": f"+9198765{index:05d}",
                    "emergency_contact_relationship": "Parent",
                    "guardian_name": f"{first}'s Guardian",
                    "guardian_phone": f"+9198760{index:05d}",
                    "fee_status": FEE_CYCLE[index % len(FEE_CYCLE)],
                },
            )
        )

    return accounts


class Command(BaseCommand):
    help = "Create or refresh fake demo users and profiles (local/staging only)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reset the password of existing demo accounts as well.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not getattr(settings, "ALLOW_DEMO_SEED", False):
            raise CommandError(
                f"Demo seeding is disabled in the {getattr(settings, 'ENVIRONMENT', 'unknown')} "
                "environment. This command must never run against production data."
            )

        password = os.environ.get("DEMO_USER_PASSWORD", "")
        if not password:
            raise CommandError(
                "DEMO_USER_PASSWORD is not set. Supply it through the environment "
                "or the staging secret manager; it is intentionally not defaulted "
                "and must not be committed."
            )
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(
                "DEMO_USER_PASSWORD does not meet the password policy: " + "; ".join(exc.messages)
            ) from exc

        created = updated = 0
        by_role: dict[str, int] = {}
        for account in build_demo_accounts():
            was_created = self._upsert(account, password, force=options["force"])
            created += int(was_created)
            updated += int(not was_created)
            by_role[account.role] = by_role.get(account.role, 0) + 1

        roster = ", ".join(f"{count} {role}" for role, count in sorted(by_role.items()))
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo data ready: {created} created, {updated} updated "
                f"({roster}) on @{DEMO_EMAIL_DOMAIN}."
            )
        )
        self.stdout.write(
            "Sign in with the value of DEMO_USER_PASSWORD. "
            "Credentials are printed nowhere and stored in no file."
        )

    def _upsert(self, account: DemoAccount, password: str, *, force: bool) -> bool:
        user = User.objects.filter(email=account.email).first()
        is_new = user is None

        if is_new:
            user = User.objects.create_user(
                email=account.email,
                password=password,
                first_name=account.first_name,
                last_name=account.last_name,
                role=account.role,
                is_staff=account.role in STAFF_ROLES,
                is_active=True,
            )
        else:
            user.first_name = account.first_name
            user.last_name = account.last_name
            user.role = account.role
            user.is_active = True
            user.is_staff = account.role in STAFF_ROLES
            if force:
                user.set_password(password)
            user.save()

        # Demo accounts are pre-verified so reviewers are not blocked behind an
        # email they cannot receive on a .invalid domain.
        if not user.is_email_verified:
            from django.utils import timezone

            user.is_email_verified = True
            user.email_verified_at = timezone.now()
            user.save(update_fields=["is_email_verified", "email_verified_at"])

        if account.role == UserRole.STUDENT:
            self._upsert_profile(
                StudentProfile, user, account.profile, next_student_id, "student_id"
            )
        elif account.role == UserRole.TRAINER:
            self._upsert_profile(
                TrainerProfile, user, account.profile, next_trainer_id, "trainer_id"
            )

        return is_new

    @staticmethod
    def _upsert_profile(model, user, fields: dict[str, Any], allocate_id, id_field: str) -> None:
        profile = model.objects.filter(user=user).first()
        if profile is None:
            model.objects.create(user=user, **{id_field: allocate_id()}, **fields)
            return
        for name, value in fields.items():
            setattr(profile, name, value)
        profile.save()
