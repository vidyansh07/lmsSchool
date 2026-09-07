"""The institution's appearance, and who may change it.

Two things are being checked, and the second is the interesting one.

The feature: a superadmin sets a brand colour, everybody's interface follows it.

The shape: this endpoint is read by *every* signed-in user on the first paint of
every page, because the interface cannot draw itself without it. That makes it
unusual — almost everything else here is scoped to a role — so the read being
open is a deliberate decision rather than an oversight, and the write being
narrow is what keeps it safe.
"""

from __future__ import annotations

import pytest

from apps.branding.models import BrandingSetting
from apps.branding.services import update_branding
from apps.common.exceptions import ApplicationError

URL = "/api/v1/branding/"
GRRAS_ORANGE = "#EF7220"


@pytest.fixture
def superadmin(db):
    from apps.accounts.models import User, UserRole

    return User.objects.create_user(
        email="super@branding.grras.invalid",
        password="Str0ng-Passphrase!42",
        first_name="Sena",
        last_name="Superadmin",
        role=UserRole.SUPERADMIN,
    )


# ---------------------------------------------------------------------------
# One row, however you get to it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_row_is_created_on_first_read():
    """Nothing has to seed it, so a fresh install is not a special case."""
    assert BrandingSetting.objects.count() == 0

    branding = BrandingSetting.current()

    assert branding.pk is not None
    assert BrandingSetting.objects.count() == 1


@pytest.mark.django_db
def test_reading_it_twice_does_not_make_a_second_one():
    first = BrandingSetting.current()
    second = BrandingSetting.current()

    assert first.pk == second.pk
    assert BrandingSetting.objects.count() == 1


@pytest.mark.django_db
def test_an_unset_colour_reads_as_null_not_empty_string(api_client_no_csrf, student_profile):
    """`""` would make every caller write the same falsy check.

    The interface reads "no colour chosen" as "use the built-in palette", and
    `null` says that plainly.
    """
    api_client_no_csrf.force_login(student_profile.user)

    body = api_client_no_csrf.get(URL).json()

    assert body["brand_color"] is None
    assert body["display_name"] is None


# ---------------------------------------------------------------------------
# Who may read it — everybody, and why that is right
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fixture", ["student_profile", "counsellor_user", "manager_user", "admin_user"]
)
def test_every_signed_in_role_can_read_it(api_client_no_csrf, request, fixture):
    """Every screen needs this to draw itself.

    Withholding it from a student would mean the product renders in the wrong
    colours for the people who use it most — a worse outcome than the
    non-secret it would be protecting.
    """
    who = request.getfixturevalue(fixture)
    user = getattr(who, "user", who)
    api_client_no_csrf.force_login(user)

    assert api_client_no_csrf.get(URL).status_code == 200


@pytest.mark.django_db
def test_nobody_anonymous_reads_it(api_client_no_csrf):
    assert api_client_no_csrf.get(URL).status_code in (401, 403)


# ---------------------------------------------------------------------------
# Who may change it — one role
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_superadmin_can_set_the_colour(api_client_no_csrf, superadmin):
    api_client_no_csrf.force_login(superadmin)

    response = api_client_no_csrf.patch(
        URL, {"brand_color": GRRAS_ORANGE, "display_name": "Grras Solutions"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert response.data["brand_color"] == GRRAS_ORANGE
    assert response.data["display_name"] == "Grras Solutions"


@pytest.mark.django_db
@pytest.mark.parametrize("fixture", ["admin_user", "manager_user", "counsellor_user"])
def test_nobody_below_a_superadmin_may_change_it(api_client_no_csrf, request, fixture):
    """Appearance is `platform.configure`, the capability an administrator does
    not hold. Changing it changes what every user sees on every screen."""
    api_client_no_csrf.force_login(request.getfixturevalue(fixture))

    response = api_client_no_csrf.patch(URL, {"brand_color": "#123456"}, format="json")

    assert response.status_code == 403
    assert BrandingSetting.current().brand_color == ""


@pytest.mark.django_db
def test_a_student_may_not_change_it(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)

    assert (
        api_client_no_csrf.patch(URL, {"brand_color": "#123456"}, format="json").status_code == 403
    )


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "value",
    ["orange", "rgb(239,114,32)", "#EF722", "#GGGGGG", "hsl(24 86% 53%)", "#EF7220ff"],
)
def test_only_hex_is_accepted(api_client_no_csrf, superadmin, value):
    """Deliberately narrow, and the reason is downstream.

    The interface derives a *legible* button colour by decomposing this into
    OKLCH, and it can only do that for hex. Accepting `hsl(...)` would store
    something that silently falls back to the default on every screen — the
    setting would appear to work and do nothing.
    """
    api_client_no_csrf.force_login(superadmin)

    response = api_client_no_csrf.patch(URL, {"brand_color": value}, format="json")

    assert response.status_code == 400, f"{value} was accepted"


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["#EF7220", "#ef7220", "#FFF", "#0d6efd"])
def test_valid_hex_in_either_case_and_length_is_accepted(api_client_no_csrf, superadmin, value):
    api_client_no_csrf.force_login(superadmin)

    assert api_client_no_csrf.patch(URL, {"brand_color": value}, format="json").status_code == 200


@pytest.mark.django_db
def test_clearing_the_colour_returns_to_the_built_in_palette(api_client_no_csrf, superadmin):
    api_client_no_csrf.force_login(superadmin)
    api_client_no_csrf.patch(URL, {"brand_color": GRRAS_ORANGE}, format="json")

    response = api_client_no_csrf.patch(URL, {"brand_color": ""}, format="json")

    assert response.status_code == 200
    assert response.data["brand_color"] is None


@pytest.mark.django_db
def test_an_unknown_field_is_named_rather_than_ignored(api_client_no_csrf, superadmin):
    api_client_no_csrf.force_login(superadmin)

    response = api_client_no_csrf.patch(URL, {"brand_colour": "#EF7220"}, format="json")

    assert response.status_code == 400
    assert "brand_colour" in str(response.data)


# ---------------------------------------------------------------------------
# The record of it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_changing_the_brand_is_audited(superadmin):
    """ "When did the app turn blue, and who did it" is a real question.

    It is tempting to treat a colour as too trivial to record. It is a setting
    that changes what every user sees on every screen.
    """
    from apps.audit.models import AuditAction, AuditLog

    update_branding(actor=superadmin, brand_color=GRRAS_ORANGE)

    entry = AuditLog.objects.filter(action=AuditAction.BRANDING_UPDATED).first()
    assert entry is not None
    assert entry.actor == superadmin
    assert entry.context["brand_color"] == GRRAS_ORANGE
    assert entry.context["changed_fields"] == ["brand_color"]


@pytest.mark.django_db
def test_setting_it_to_what_it_already_is_records_nothing(superadmin):
    """An audit trail full of no-ops is an audit trail nobody reads."""
    from apps.audit.models import AuditAction, AuditLog

    update_branding(actor=superadmin, brand_color=GRRAS_ORANGE)
    before = AuditLog.objects.filter(action=AuditAction.BRANDING_UPDATED).count()

    update_branding(actor=superadmin, brand_color=GRRAS_ORANGE)

    assert AuditLog.objects.filter(action=AuditAction.BRANDING_UPDATED).count() == before


@pytest.mark.django_db
def test_the_service_refuses_a_bad_colour_too(superadmin):
    """Enforced in the service, not only the serializer, so the Django admin
    and any future management command obey the same rule."""
    from django.core.exceptions import ValidationError

    with pytest.raises((ValidationError, ApplicationError)):
        update_branding(actor=superadmin, brand_color="not-a-colour")


@pytest.mark.django_db
def test_who_changed_it_is_kept(superadmin):
    update_branding(actor=superadmin, display_name="Grras Solutions")

    assert BrandingSetting.current().updated_by == superadmin
