"""Placements — where a student ended up, and the offers on the way there.

One record per offer, not per student: somebody interviews at four places,
turns two down and joins the third, and all of that is the placement
officer's working record. The student's own `open_to_placement` flag says
whether they want to be put forward at all; this app says what happened when
they were.

Deliberately *not* here: employers, openings and applications. A job board —
companies registering, posting vacancies, students applying — is a different
product, and nothing in the institute's placement work needs it: the officer
knows the companies, rings them, and records the outcome. `company` is a
name typed by whoever recorded the offer, with `company_key` to group the
spellings, the same shape `organisation.College` uses for the colleges
students come from.

The interview and soft-skills *work* already has a home: the activity
catalogue's `mock-interview`, `hr-interview`, `resume-review`,
`communication-practice` and `placement-call` types (`apps.work`). This app
records the result of that work, and does not duplicate it.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteBaseModel, SoftDeleteQuerySet, soft_delete_managers


class PlacementStatus(models.TextChoices):
    """Where an offer stands. In the order one moves through."""

    OFFERED = "offered", _("Offered")
    ACCEPTED = "accepted", _("Accepted")
    JOINED = "joined", _("Joined")
    DECLINED = "declined", _("Declined by the student")
    WITHDRAWN = "withdrawn", _("Withdrawn by the company")


#: The statuses that mean the student has a job out of this: what "placed"
#: counts. `OFFERED` is not one of them — an offer nobody has accepted is not
#: a placement, and counting it would overstate every number on the screen.
PLACED_STATUSES = frozenset({PlacementStatus.ACCEPTED, PlacementStatus.JOINED})

#: The statuses that are over without a job. Kept rather than deleted: "four
#: interviews, three declined" is the placement officer's actual record.
CLOSED_STATUSES = frozenset({PlacementStatus.DECLINED, PlacementStatus.WITHDRAWN})


def company_key(name: str) -> str:
    """How two spellings of one company are recognised as the same employer.

    Whitespace collapsed and case folded — not fuzzy. "infosys" and
    "Infosys  Ltd" are different employers to this function, and should be:
    guessing that they are the same would merge two real records on a
    coincidence of prefix.
    """
    return " ".join((name or "").split()).casefold()


class PlacementQuerySet(SoftDeleteQuerySet):
    def with_related(self):
        return self.select_related(
            "student",
            "student__user",
            "branch",
            "enrollment",
            "enrollment__course",
            "created_by",
        )

    def placed(self):
        return self.filter(status__in=PLACED_STATUSES)


class Placement(SoftDeleteBaseModel):
    """One offer made to one student, and what became of it."""

    student = models.ForeignKey(
        "students.StudentProfile",
        on_delete=models.PROTECT,
        related_name="placements",
        verbose_name=_("student"),
    )
    #: Which course got them the interview. Optional: a student placed off
    #: the back of two courses, or before any enrolment finished, is a real
    #: case and must not be unrecordable.
    enrollment = models.ForeignKey(
        "enrollments.Enrollment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="placements",
        verbose_name=_("enrolment"),
    )
    #: Denormalised from the student at creation time, so scoping a list to a
    #: centre never joins through the student — the same reason
    #: `work.Activity.batch` is denormalised from its enrolment.
    branch = models.ForeignKey(
        "organisation.Branch",
        on_delete=models.PROTECT,
        related_name="placements",
        verbose_name=_("centre"),
    )
    company = models.CharField(_("company"), max_length=120)
    #: `company_key(company)`, stored so "every offer from Infosys" is an
    #: indexed lookup rather than a scan with a case-insensitive match.
    company_key = models.CharField(_("company key"), max_length=120, db_index=True)
    role_title = models.CharField(_("role"), max_length=120)
    location = models.CharField(_("location"), max_length=80, blank=True)
    status = models.CharField(
        _("status"),
        max_length=12,
        choices=PlacementStatus.choices,
        default=PlacementStatus.OFFERED,
    )
    #: Annual, in rupees. Nullable because an offer whose package has not been
    #: stated yet is a real offer; a zero would read as "unpaid".
    annual_package = models.DecimalField(
        _("annual package"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    offered_on = models.DateField(_("offered on"))
    joined_on = models.DateField(_("joined on"), null=True, blank=True)
    #: Why an offer was declined or withdrawn, or anything else worth keeping.
    notes = models.TextField(_("notes"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recorded_placements",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects, all_objects = soft_delete_managers(PlacementQuerySet)

    class Meta(SoftDeleteBaseModel.Meta):
        verbose_name = _("placement")
        verbose_name_plural = _("placements")
        ordering = ("-offered_on", "-created_at")
        indexes = [
            models.Index(fields=["student", "-offered_on"], name="placement_student_idx"),
            models.Index(fields=["branch", "status"], name="placement_branch_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company} — {self.role_title}"

    @property
    def is_placed(self) -> bool:
        """Whether this offer means the student has a job out of it."""
        return self.status in PLACED_STATUSES
