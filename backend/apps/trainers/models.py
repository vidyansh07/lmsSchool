"""Trainer profile.

Like the student profile, this is kept out of ``accounts.User`` so the
authentication table stays small.

Forward compatibility: course and batch assignment are later phases, so no
scheduling fields exist here yet. What does exist is the hook they will need —
``is_accepting_assignments`` and ``skills`` — so a future ``Batch.trainer``
foreign key and a "find an available trainer with skill X" query can be added
without reshaping this table.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel, UUIDPrimaryKeyModel
from apps.common.validators import validate_no_control_characters, validate_professional_links

MAX_SKILLS = 30
MAX_SKILL_LENGTH = 50


class TrainerProfile(UUIDPrimaryKeyModel, TimeStampedModel):
    #: Fields a trainer may edit on their own record. Everything else —
    #: identifiers, availability for assignment, account status — is
    #: administrator-only.
    SELF_EDITABLE_FIELDS = (
        "professional_title",
        "bio",
        "skills",
        "expertise",
        "qualifications",
        "years_of_experience",
        "professional_links",
    )

    COMPLETION_FIELDS = (
        "professional_title",
        "bio",
        "skills",
        "expertise",
        "qualifications",
        "years_of_experience",
    )

    trainer_id = models.CharField(
        _("trainer ID"),
        max_length=20,
        unique=True,
        editable=False,
        help_text=_("Human-readable identifier, e.g. GRS-T-00007. Allocated by the system."),
    )
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="trainer_profile",
    )

    professional_title = models.CharField(
        _("professional title"),
        max_length=150,
        blank=True,
        validators=[validate_no_control_characters],
        help_text=_("For example: Senior Linux Trainer."),
    )
    bio = models.TextField(_("biography"), max_length=2000, blank=True)
    skills = ArrayField(
        models.CharField(max_length=MAX_SKILL_LENGTH),
        verbose_name=_("skills"),
        default=list,
        blank=True,
        size=MAX_SKILLS,
        help_text=_("Short tags, e.g. Python, RHCSA, Networking."),
    )
    expertise = models.TextField(
        _("areas of expertise"),
        max_length=1000,
        blank=True,
        help_text=_("Narrative description of specialisation."),
    )
    qualifications = models.TextField(
        _("qualifications and certifications"), max_length=1000, blank=True
    )
    years_of_experience = models.PositiveSmallIntegerField(
        _("years of experience"),
        null=True,
        blank=True,
        validators=[MaxValueValidator(70)],
    )
    professional_links = models.JSONField(
        _("professional links"),
        default=dict,
        blank=True,
        validators=[validate_professional_links],
        help_text=_("Optional map of linkedin / github / website to HTTPS URLs."),
    )

    is_accepting_assignments = models.BooleanField(
        _("accepting assignments"),
        default=True,
        db_index=True,
        help_text=_(
            "Availability for future course and batch assignment. Separate from "
            "account status: a trainer can be active but unavailable."
        ),
    )

    class Meta:
        verbose_name = _("trainer profile")
        verbose_name_plural = _("trainer profiles")
        ordering = ("trainer_id",)
        indexes = [
            models.Index(
                fields=["is_accepting_assignments", "-created_at"], name="trainer_avail_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.trainer_id} ({self.user.email})"

    @property
    def completion_percent(self) -> int:
        filled = sum(1 for field in self.COMPLETION_FIELDS if getattr(self, field, None))
        return round(filled * 100 / len(self.COMPLETION_FIELDS))

    @property
    def is_profile_complete(self) -> bool:
        return self.completion_percent == 100
