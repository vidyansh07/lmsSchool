"""One staff member's record of work: who may read it, and what it says.

The owner's decision (26 October 2026): a counsellor's record — every
student they admitted and what they did — is for administrators, and for the
counsellor themselves. A manager does not see it.

What is pinned:

- administrators and superadmins read anybody's; a person reads their own;
  a manager reads nobody's, not even a trainer's, and a colleague reads none;
- the counters count what the person actually did, from the system's own
  record of who did it;
- a voided receipt credits nobody — otherwise voiding one would be a way to
  inflate a figure;
- a line that counts zero is left out, so the shape of a record says what
  the job was;
- the window is inclusive at both ends and bounded, and a backwards one is
  refused rather than silently returning nothing;
- the timeline says when it was cut rather than letting the length imply it.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts import staff_record
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.fees import services as fee_services

pytestmark = pytest.mark.django_db


def url(user, **query) -> str:
    base = f"/api/v1/users/{user.pk}/record/"
    if not query:
        return base
    return base + "?" + "&".join(f"{key}={value}" for key, value in query.items())


def keys(record) -> set[str]:
    return {counter.key for counter in record.counters}


def counter(record, key):
    return next(item for item in record.counters if item.key == key)


# ---------------------------------------------------------------------------
# Who may read it
# ---------------------------------------------------------------------------


def test_an_administrator_reads_anybody_s(admin_user, counsellor_user):
    record = staff_record.build(actor=admin_user, person=counsellor_user)
    assert record.person["id"] == str(counsellor_user.pk)


def test_a_person_reads_their_own(counsellor_user):
    # Ownership, not a grant. Somebody who cannot see their own admissions
    # count will ask a colleague to read it to them.
    record = staff_record.build(actor=counsellor_user, person=counsellor_user)
    assert record.person["id"] == str(counsellor_user.pk)


def test_a_manager_reads_nobody_s(manager_user, counsellor_user):
    with pytest.raises(AuthorityError):
        staff_record.build(actor=manager_user, person=counsellor_user)


def test_a_manager_does_not_read_a_trainer_s_either(manager_user, trainer):
    # The decision covers trainers and placement the same way. A manager keeps
    # the trainer oversight they already have -- reviews, requirements, class
    # reports -- which is a different screen and a different capability.
    with pytest.raises(AuthorityError):
        staff_record.build(actor=manager_user, person=trainer)


def test_one_counsellor_does_not_read_another_s(counsellor_user, manager_user):
    with pytest.raises(AuthorityError):
        staff_record.build(actor=manager_user, person=counsellor_user)


def test_a_student_reads_nobody_s(student_profile, counsellor_user):
    with pytest.raises(AuthorityError):
        staff_record.build(actor=student_profile.user, person=counsellor_user)


# ---------------------------------------------------------------------------
# What it counts
# ---------------------------------------------------------------------------


def test_money_is_credited_to_whoever_recorded_it(admin_user, counsellor_user, enrollment):
    plan = fee_services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount=Decimal("24000")
    )
    fee_services.record_payment(
        plan=plan, actor=counsellor_user, amount=Decimal("5000"), method="cash"
    )

    record = staff_record.build(actor=admin_user, person=counsellor_user)

    collected = counter(record, "collected")
    assert collected.count == 1
    assert collected.amount == Decimal("5000")


def test_a_voided_receipt_credits_nobody(admin_user, counsellor_user, enrollment):
    plan = fee_services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount=Decimal("24000")
    )
    payment = fee_services.record_payment(
        plan=plan, actor=counsellor_user, amount=Decimal("5000"), method="cash"
    )
    fee_services.void_payment(actor=counsellor_user, payment=payment, reason="Entered twice.")

    record = staff_record.build(actor=admin_user, person=counsellor_user)

    # Otherwise voiding a receipt would be a way to inflate a figure.
    assert "collected" not in keys(record)


def test_a_line_that_counts_nothing_is_left_out(admin_user, counsellor_user):
    record = staff_record.build(actor=admin_user, person=counsellor_user)

    # A counsellor's record listing "0 class reports" and a trainer's listing
    # "0 receipts" is a form, not a record.
    assert record.counters == []


def test_the_record_shows_the_person_asked_about(admin_user, counsellor_user):
    record = staff_record.build(actor=admin_user, person=counsellor_user)
    assert record.person["name"] == "Kiran Counsellor"
    assert record.person["role"] == "counsellor"


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------


def test_the_window_includes_both_ends(admin_user, counsellor_user, enrollment):
    plan = fee_services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount=Decimal("24000")
    )
    today = timezone.localdate()
    fee_services.record_payment(
        plan=plan, actor=counsellor_user, amount=Decimal("5000"), method="cash", paid_on=today
    )

    # "to today" has to include today, which a naive midnight bound does not.
    record = staff_record.build(actor=admin_user, person=counsellor_user, start=today, end=today)
    assert counter(record, "collected").count == 1


def test_a_backwards_window_is_refused(admin_user, counsellor_user):
    today = timezone.localdate()
    with pytest.raises(ApplicationError):
        staff_record.build(
            actor=admin_user,
            person=counsellor_user,
            start=today,
            end=today - timedelta(days=1),
        )


def test_an_unbounded_span_is_refused(admin_user, counsellor_user):
    today = timezone.localdate()
    with pytest.raises(ApplicationError):
        staff_record.build(
            actor=admin_user,
            person=counsellor_user,
            start=today - timedelta(days=staff_record.MAX_DAYS + 1),
            end=today,
        )


def test_it_defaults_to_the_last_month(admin_user, counsellor_user):
    record = staff_record.build(actor=admin_user, person=counsellor_user)
    assert (record.end - record.start).days == 30


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_the_endpoint_returns_the_record(api_client_no_csrf, admin_user, counsellor_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(url(counsellor_user))

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["person"]["id"] == str(counsellor_user.pk)
    assert body["timeline_truncated"] is False


def test_the_endpoint_refuses_a_manager(api_client_no_csrf, manager_user, counsellor_user):
    api_client_no_csrf.force_login(manager_user)
    response = api_client_no_csrf.get(url(counsellor_user))
    assert response.status_code == 403


def test_the_endpoint_lets_somebody_read_their_own(api_client_no_csrf, counsellor_user):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.get(url(counsellor_user))
    assert response.status_code == 200


def test_a_guessed_id_is_a_404_not_an_authority_error(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get("/api/v1/users/00000000-0000-0000-0000-000000000000/record/")
    # Resolved through the scoped queryset first, so a guessed uuid never
    # answers in a way that confirms an account exists.
    assert response.status_code == 404


def test_the_endpoint_reads_the_dates_it_is_given(api_client_no_csrf, admin_user, counsellor_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(url(counsellor_user, start="2026-04-01", end="2026-06-30"))

    assert response.status_code == 200
    body = response.json()
    assert body["start"] == "2026-04-01"
    assert body["end"] == "2026-06-30"
