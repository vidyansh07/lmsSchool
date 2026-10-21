"""Organisational structure: the centres an institution is actually run by.

A branch is deliberately not a tenant. There is one database, one course
catalogue and one academic policy, because GRRAS teaches the same syllabus at
every centre and a manager comparing two branches is a thing the product is
for. What a branch bounds is *people and classes* — who a manager may see, and
which classes appear on their screens.

Closed, not deleted
-------------------
``Branch`` inherits :class:`~apps.common.models.BaseModel` rather than
:class:`~apps.common.models.SoftDeleteBaseModel`. A centre is *closed*
(``is_active=False``), never removed: every ``PROTECT``-ed foreign key pointing
at it stays valid, its history stays readable, and it never enters the recycle
bin — which sidesteps the question of what a deleted branch's scope would even
mean for the accounts still stamped with it.

A code somebody types
---------------------
``code`` is unique and human-chosen ("JAI", "PUNE"). There are a handful of
centres and an operator names them, so there is no ``next_branch_code()``
sequence here of the kind :mod:`apps.common.identifiers` allocates for the
records a system generates in bulk.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters


class BranchQuerySet(models.QuerySet):
    def with_related(self):
        """No relations to pull: a branch is a leaf.

        Defined anyway because every listed model in this codebase answers
        ``with_related()``, and a caller that has to know which models do and
        which do not is a caller that will eventually guess wrong.
        """
        return self

    def active(self):
        return self.filter(is_active=True)


class Branch(BaseModel):
    """One centre."""

    code = models.CharField(
        _("code"),
        max_length=20,
        unique=True,
        validators=[validate_no_control_characters],
        help_text=_("Short identifier an operator chooses, e.g. JAI or PUNE."),
    )
    name = models.CharField(_("name"), max_length=120, validators=[validate_no_control_characters])
    city = models.CharField(
        _("city"), max_length=80, blank=True, validators=[validate_no_control_characters]
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_(
            "A closed centre keeps its people and classes readable; it is "
            "simply not offered when somebody is choosing where to put a new "
            "record."
        ),
    )

    objects = BranchQuerySet.as_manager()

    class Meta:
        verbose_name = _("branch")
        verbose_name_plural = _("branches")
        ordering = ("code",)
        indexes = [models.Index(fields=["is_active", "code"], name="branch_active_code_idx")]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class CollegeQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class College(BaseModel):
    """A school, college or university students come from.

    The student record has carried the institution as free text since the
    beginning, and free text drifts: "Arya College of Engineering", "Arya
    college", "ARYA COLLEGE OF ENGG" are one place and three rows, and no
    report can add them up. The demo data looks tidy only because a seed wrote
    it; a year of counsellors typing it will not.

    So it becomes something to pick. A counsellor who cannot find the college
    adds it there and then — the alternative is that they type it into the old
    free-text box and the drift starts again — and the next person picks what
    they added.

    ``StudentProfile.institution`` is deliberately untouched. It holds a
    thousand real students' answers, some of which name an employer rather
    than a college, and discarding them to make a foreign key tidy would be
    losing data to gain a diagram. The two live side by side: the link is what
    a report groups by, and the text is what somebody wrote.
    """

    name = models.CharField(
        _("name"),
        max_length=200,
        validators=[validate_no_control_characters],
    )
    #: The name with its case and spacing flattened, so two spellings of one
    #: college collide on the unique constraint instead of both being stored.
    #: Derived on save and never edited: a key somebody can type is a key
    #: somebody can get wrong.
    match_key = models.CharField(_("match key"), max_length=200, unique=True, editable=False)
    city = models.CharField(
        _("city"), max_length=80, blank=True, validators=[validate_no_control_characters]
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_(
            "A college that is no longer offered when choosing. Students "
            "already attached to it keep it — history does not stop being true."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="colleges_added",
    )

    objects = CollegeQuerySet.as_manager()

    class Meta:
        verbose_name = _("college")
        verbose_name_plural = _("colleges")
        ordering = ("name",)
        indexes = [models.Index(fields=["is_active", "name"], name="college_active_name_idx")]

    def __str__(self) -> str:
        return f"{self.name} — {self.city}" if self.city else self.name

    @staticmethod
    def key_for(name: str) -> str:
        """The spelling-insensitive key two entries of one college share."""
        return " ".join(name.split()).casefold()

    def save(self, *args, **kwargs):
        self.name = " ".join(self.name.split())
        self.match_key = self.key_for(self.name)
        super().save(*args, **kwargs)
