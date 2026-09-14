"""Platform configuration, stored as data rather than shipped in a release.

The values here are the ones an operator asks about on the phone: what does the
institution call itself in the emails it sends, where does somebody write when
they are stuck, do notification emails go out at all this week, how long is an
export kept, how large a file may a trainer attach. None of them is an academic
rule and none of them is a boot-time secret, which is exactly the gap this
table fills.

One row, with named columns
---------------------------
A key/value bag would have been fewer migrations and far worse: no
``full_clean``, no ``choices``, no schema for drf-spectacular to publish and
nothing for a ``StrictSerializer`` to be strict about, so the first mistyped
key becomes a silently ignored setting nobody can find. Named columns cost one
migration per setting, and that is the right cost — adding a setting is a
product decision and should show up in a diff.

"One row" is a ``BooleanField`` that is always ``True`` under a unique
constraint. :class:`~apps.academics.models.AcademicPolicy` spends a conditional
constraint on the same guarantee because it has a second scope to distinguish;
this model has none, so the boolean says it more plainly and the database still
enforces it.

The boundary against ``config/settings``
----------------------------------------
A value belongs here when changing it is an operator's decision that takes
effect on the next request. It belongs in ``config/settings/*`` when changing
it is a deployment, or when reading it from the database would be a security
regression — everything ``config.settings.guards.require_setting`` refuses to
boot without, the CSP, the throttle rates, the scanner switches. Those exist to
stop an unconfigured production starting at all, and a database default would
start one.

Not per-branch
--------------
The institution has one name and one support address. A centre's own address is
a property of that centre and belongs on the branch record, not here — the same
reason ``AcademicPolicy`` is institution-wide.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.common.validators import validate_no_control_characters

#: The answer before anybody has configured anything. These are code defaults,
#: not policy: a fresh install behaves sensibly, and an institution that cares
#: replaces them on the settings screen.
#:
#: Every key here is read by real code. A setting nothing consumes is a promise
#: to an operator that the system does not keep.
DEFAULT_SETTINGS: dict[str, object] = {
    "institution_name": "Grras Solutions",
    "support_email": "",
    "support_phone": "",
    "notification_email_enabled": True,
    "export_retention_days": 14,
    "resource_upload_max_mb": 25,
}

#: Every configurable setting, in one list, so the API, the admin and the
#: resolver cannot drift apart. Adding a setting means adding a field and a line
#: here.
SETTING_FIELDS: tuple[str, ...] = tuple(DEFAULT_SETTINGS)


class SystemSetting(BaseModel):
    """The institution's own configuration. There is exactly one of these."""

    # --- Who the institution is, as the people it writes to see it
    institution_name = models.CharField(
        _("institution name"),
        max_length=160,
        blank=True,
        default="",
        validators=[validate_no_control_characters],
        help_text=_("Signed at the foot of every email this system sends."),
    )
    support_email = models.EmailField(_("support email"), max_length=254, blank=True, default="")
    support_phone = models.CharField(
        _("support phone"),
        max_length=32,
        blank=True,
        default="",
        validators=[validate_no_control_characters],
    )

    # --- Operational switches and windows
    notification_email_enabled = models.BooleanField(
        _("send notification email"),
        default=True,
        help_text=_(
            "Turning this off suppresses delivery only. The in-app notification "
            "is still written, so nothing is lost."
        ),
    )
    export_retention_days = models.PositiveSmallIntegerField(
        _("keep exports for (days)"),
        default=14,
        help_text=_("How long a finished export stays downloadable before it expires."),
    )
    resource_upload_max_mb = models.PositiveSmallIntegerField(
        _("largest upload (MB)"),
        default=25,
        help_text=_("Applies to course resources and assignment attachments."),
    )

    #: Always ``True``. The unique constraint on it is what makes "one row" a
    #: fact about the database rather than a convention somebody eventually
    #: breaks from a management command.
    singleton = models.BooleanField(default=True, editable=False)

    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="system_setting_updates",
    )

    class Meta:
        verbose_name = _("institution settings")
        verbose_name_plural = _("institution settings")
        constraints = [
            models.UniqueConstraint(fields=["singleton"], name="systemsetting_one_row"),
        ]

    def __str__(self) -> str:
        return self.institution_name or "Institution settings"

    def clean(self) -> None:
        """Bound the two numeric settings, so neither can be turned off.

        A retention of zero would expire an export the moment it finished,
        which reads to the person who requested it as a broken download rather
        than as a policy; and an upload ceiling an operator can raise without
        limit is an upload ceiling that is not one.
        """
        from django.core.exceptions import ValidationError

        errors: dict[str, str] = {}
        if self.export_retention_days is not None and not (1 <= self.export_retention_days <= 365):
            errors["export_retention_days"] = "Keep exports for between 1 and 365 days."
        if self.resource_upload_max_mb is not None and not (
            1 <= self.resource_upload_max_mb <= 100
        ):
            errors["resource_upload_max_mb"] = "The upload ceiling must be between 1 and 100 MB."
        if errors:
            raise ValidationError(errors)
