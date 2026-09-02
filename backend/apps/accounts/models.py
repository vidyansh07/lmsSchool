"""Identity models.

The custom user model was created in Phase 0 on purpose: swapping
``AUTH_USER_MODEL`` after tables exist is one of the most painful migrations in
Django, and every LMS table carries a foreign key to it. Phase 1 extends that
same model rather than introducing a second one.

Design notes
------------
* Email is the login identifier. Students and trainers are onboarded by email;
  a separate username would be a second thing to keep unique and support.
* ``role`` is a single coarse role stored on the user. It is the input to the
  capability matrix in :mod:`apps.accounts.roles`, which is the sole authority
  for authorization decisions.
* Domain detail lives in the profile models (``apps.students``,
  ``apps.trainers``), so the authentication table stays small and stable.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import UUIDPrimaryKeyModel
from apps.common.uploads import profile_image_upload_to
from apps.common.validators import validate_person_name, validate_phone_number

from .managers import UserManager
from .roles import Capability, UserRole, capabilities_for, has_capability

__all__ = [
    "AccountToken",
    "Capability",
    "TokenPurpose",
    "User",
    "UserRole",
]


class User(UUIDPrimaryKeyModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        _("email address"),
        unique=True,
        max_length=254,
        help_text=_("Used to sign in. Stored lower-cased."),
    )
    first_name = models.CharField(
        _("first name"), max_length=100, validators=[validate_person_name]
    )
    last_name = models.CharField(
        _("last name"), max_length=100, blank=True, validators=[validate_person_name]
    )
    phone = models.CharField(
        _("phone"), max_length=20, blank=True, validators=[validate_phone_number]
    )
    profile_image = models.ImageField(
        _("profile image"),
        upload_to=profile_image_upload_to,
        blank=True,
        null=True,
        max_length=255,
        help_text=_(
            "Stored under MEDIA_ROOT, which is not web-served. Delivered through "
            "an authenticated view."
        ),
    )
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
        db_index=True,
        help_text=_("Authoritative role used for server-side authorization."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_("Deactivate instead of deleting to preserve audit history."),
    )
    is_staff = models.BooleanField(
        _("staff status"), default=False, help_text=_("Grants access to the Django admin.")
    )
    is_email_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Set once the user confirms an emailed verification link."),
    )
    email_verified_at = models.DateTimeField(_("email verified at"), null=True, blank=True)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ("email",)
        constraints = [
            # Belt-and-braces against case-variant duplicate accounts, which
            # would otherwise allow two logins for one human.
            models.UniqueConstraint(models.functions.Lower("email"), name="user_email_ci_unique"),
        ]
        indexes = [
            # The admin list filters on role and status together and orders by
            # creation date; one composite index serves the common query.
            models.Index(fields=["role", "is_active"], name="user_role_active_idx"),
            models.Index(fields=["-created_at"], name="user_created_idx"),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email).strip().lower()

    def save(self, *args, **kwargs):
        # Normalise here too: the admin and data migrations bypass ``clean``.
        self.email = self.__class__.objects.normalize_email(self.email).strip().lower()
        return super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name

    @property
    def capabilities(self) -> frozenset[str]:
        """Everything this user is permitted to do, resolved from the matrix."""
        return capabilities_for(self.role, is_superuser=self.is_superuser)

    def has_capability(self, capability: str) -> bool:
        return has_capability(self, capability)

    @property
    def is_admin_role(self) -> bool:
        return self.role == UserRole.ADMIN or self.is_superuser

    @property
    def is_trainer_role(self) -> bool:
        return self.role == UserRole.TRAINER

    @property
    def is_student_role(self) -> bool:
        return self.role == UserRole.STUDENT


class TokenPurpose(models.TextChoices):
    EMAIL_VERIFICATION = "email_verification", _("Email verification")
    PASSWORD_RESET = "password_reset", _("Password reset")


class AccountTokenQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(used_at__isnull=True, expires_at__gt=timezone.now())


class AccountToken(models.Model):
    """Single-use, expiring token for email verification and password reset.

    Security properties:

    * **Only a hash is stored.** The raw token exists in the emailed link and
      nowhere else, so a database read cannot be turned into account takeover.
      Lookup is by hash, so this costs nothing.
    * **Single use.** ``used_at`` is stamped inside the same transaction that
      consumes the token, and a used token is rejected thereafter.
    * **Expiring.** Password-reset tokens are short-lived; verification links
      are allowed longer because they are less powerful.
    * **Superseding.** Issuing a new token of a purpose invalidates that user's
      outstanding ones, so an old link in an inbox stops working.

    The raw value is never logged and never written to an audit record.
    """

    TOKEN_BYTES = 32  # 256 bits of entropy

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="account_tokens"
    )
    purpose = models.CharField(max_length=32, choices=TokenPurpose.choices, db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AccountTokenQuerySet.as_manager()

    class Meta:
        verbose_name = _("account token")
        verbose_name_plural = _("account tokens")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "purpose", "used_at"], name="token_user_purpose_idx"),
        ]

    def __str__(self) -> str:
        # Deliberately never renders the hash or any part of the token.
        return f"{self.get_purpose_display()} for {self.user_id} ({self.created_at:%Y-%m-%d})"

    @staticmethod
    def hash_token(raw_token: str) -> str:
        """SHA-256 of the raw token.

        A plain hash is correct here (unlike for passwords): the token is
        high-entropy random, so there is nothing to brute-force, and lookup must
        stay a single indexed query.
        """
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= timezone.now()

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    @classmethod
    def ttl_for(cls, purpose: str) -> timedelta:
        """Lifetime per purpose, read from settings so emails cannot disagree."""
        from django.conf import settings

        if purpose == TokenPurpose.PASSWORD_RESET:
            return timedelta(hours=settings.AUTH_TOKEN_RESET_TTL_HOURS)
        return timedelta(days=settings.AUTH_TOKEN_VERIFICATION_TTL_DAYS)

    @classmethod
    def issue(cls, *, user: User, purpose: str) -> tuple[AccountToken, str]:
        """Create a token, invalidating the user's outstanding ones first.

        Returns ``(token_record, raw_token)``. The caller must put the raw value
        into the outgoing email and then discard it.
        """
        now = timezone.now()
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=now)
        raw_token = secrets.token_urlsafe(cls.TOKEN_BYTES)
        record = cls.objects.create(
            user=user,
            purpose=purpose,
            token_hash=cls.hash_token(raw_token),
            expires_at=now + cls.ttl_for(purpose),
        )
        return record, raw_token

    def consume(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])
