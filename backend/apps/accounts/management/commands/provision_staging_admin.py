"""Safely provision one application administrator in staging.

No password or verification state is accepted by this command. A new account
receives the application's ordinary one-time password-setup link and email
verification link, and must complete both flows itself.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from apps.accounts.models import User, UserRole
from apps.accounts.services import create_user, request_email_verification
from apps.organisation.models import Branch


class Command(BaseCommand):
    help = (
        "Create one staging application administrator without setting a password "
        "or bypassing email verification. Dry-run unless --apply is supplied."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)
        parser.add_argument("--branch-code", required=True)
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create the account and request the normal setup/verification emails.",
        )
        parser.add_argument(
            "--resend-verification",
            action="store_true",
            help="For an existing matching account, issue a fresh verification link.",
        )

    def handle(self, *args, **options) -> None:
        if getattr(settings, "ENVIRONMENT", "") != "staging":
            raise CommandError("This command only runs with the staging settings module.")

        email = User.objects.normalize_email(options["email"]).strip().lower()
        first_name = options["first_name"].strip()
        last_name = options["last_name"].strip()
        branch_code = options["branch_code"].strip()

        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("Enter a valid email address.") from exc
        if not first_name or not last_name:
            raise CommandError("Both --first-name and --last-name are required.")

        branch = Branch.objects.filter(code__iexact=branch_code, is_active=True).first()
        if branch is None:
            raise CommandError(f"No active centre has code {branch_code!r}.")

        existing = (
            User.objects.select_related("branch", "custom_role").filter(email__iexact=email).first()
        )
        if existing is not None:
            self._handle_existing(
                existing,
                first_name=first_name,
                last_name=last_name,
                branch=branch,
                apply=options["apply"],
                resend_verification=options["resend_verification"],
            )
            return

        if not options["apply"]:
            self.stdout.write(
                f"Would create application admin {email} at {branch.code}; no data changed."
            )
            return

        user = create_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.ADMIN,
            branch=branch,
            actor=None,
            password=None,
            send_invitation=True,
        )
        request_email_verification(user=user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Created application admin {user.email} at {branch.code}. "
                "Password setup and email verification were requested through the normal "
                "mail workflow; confirm delivery with the configured provider."
            )
        )

    def _handle_existing(
        self,
        user: User,
        *,
        first_name: str,
        last_name: str,
        branch: Branch,
        apply: bool,
        resend_verification: bool,
    ) -> None:
        mismatches = []
        if user.first_name != first_name:
            mismatches.append("first name")
        if user.last_name != last_name:
            mismatches.append("last name")
        if user.role != UserRole.ADMIN:
            mismatches.append("role")
        if user.custom_role_id is not None:
            mismatches.append("custom role")
        if user.branch_id != branch.pk:
            mismatches.append("centre")
        if not user.is_active:
            mismatches.append("active status")
        if user.is_staff or user.is_superuser:
            mismatches.append("Django staff privilege")
        if mismatches:
            raise CommandError(
                "An account with this email already exists but does not match the approved "
                f"application-admin profile ({', '.join(mismatches)}). Nothing was changed."
            )

        if resend_verification and not user.is_email_verified:
            if apply:
                request_email_verification(user=user)
                self.stdout.write(
                    f"Existing application admin {user.email} is unchanged; a fresh email "
                    "verification link was requested."
                )
            else:
                self.stdout.write(
                    f"Would request a fresh verification link for {user.email}; no data changed."
                )
            return

        verification = "verified" if user.is_email_verified else "not yet verified"
        self.stdout.write(
            f"Application admin {user.email} already matches the approved profile and is "
            f"{verification}; no data changed."
        )
