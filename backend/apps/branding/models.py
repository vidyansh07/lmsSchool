"""What this institution looks like.

One row, holding the settings that decide the interface's appearance rather
than its behaviour. Separate from `academics.AcademicPolicy` on purpose: that
holds rules which change what the system *does* — pass marks, attendance
thresholds — and a colour is not one of those. Mixing them would mean the
screen for changing a passing percentage also changed the logo.

Why a singleton rather than a settings file
-------------------------------------------
A brand colour is chosen by the institution, not by whoever deploys the
software, and it is changed by someone in an office rather than by a release.
Putting it in `settings.py` would mean a code change and a restart to alter a
shade of orange.

Why one row rather than one per tenant
--------------------------------------
This install serves one institution. A `tenant` foreign key would be honest
about a future that does not exist yet and would have to be carried by every
query in the meantime. The row is fetched through `current()`, so becoming
per-tenant later is a change to that one function and a migration, not a sweep
through the codebase.
"""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel

#: Hex, three or six digits. Deliberately narrow: the frontend derives a legible
#: button colour from this by decomposing it, and it can only do that for a hex
#: value. Accepting `hsl(...)` here would store something that silently falls
#: back to the default orange on every screen.
HEX_COLOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message=_("Use a hex colour such as #EF7220."),
)


class BrandingSetting(BaseModel):
    """The institution's appearance. Exactly one row; see `current()`."""

    brand_color = models.CharField(
        _("brand colour"),
        max_length=7,
        blank=True,
        default="",
        validators=[HEX_COLOR],
        help_text=_(
            "Hex, e.g. #EF7220. Blank uses the built-in Grras palette. The "
            "interface derives a darker shade for buttons and links so text on "
            "them stays legible, whatever colour is chosen."
        ),
    )
    display_name = models.CharField(
        _("institution name"),
        max_length=120,
        blank=True,
        default="",
        help_text=_("Shown in the interface. Blank uses the product name."),
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = _("branding")
        verbose_name_plural = _("branding")

    def __str__(self) -> str:
        return self.display_name or "Branding"

    @classmethod
    def current(cls) -> BrandingSetting:
        """The one row, created on first read.

        Every caller goes through here, so "there is exactly one" is enforced in
        one place rather than by everyone remembering to use `first()`.
        """
        instance = cls.objects.order_by("created_at").first()
        if instance is None:
            instance = cls.objects.create()
        return instance
