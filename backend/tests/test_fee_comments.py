"""Comment threads on a payment and on an instalment.

A fee row that is not settled always has a story — a cheque sitting with the
bank, a father who asked for the 15th, a brother paying for both — and until
now the only places to put it were `FeePayment.note` (one line, written at the
counter, printed on the receipt) and the audit log (what the system was told
to change). Neither holds a conversation between colleagues about one row.

What is pinned here:

- a comment hangs off exactly one payment or one instalment, never both and
  never neither;
- the thread reads oldest first, and nothing in it can be edited or deleted;
- writing one needs `fee.manage_any`, the authority that recorded the payment;
  reading one needs `fee.view_any`; a trainer and a student have neither;
- a student never sees a comment, on any route, because a desk must be able to
  write "chasing is pointless until the exam" without composing it for them;
- a row at another centre is the 404 a guessed id gets;
- the audit entry records *which* row was commented on and how long the text
  was, never the text — the audit trail is read far more widely than the fee
  screen;
- the counts the screens show come from one query, not one per row.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.audit.models import AuditAction, AuditLog
from apps.common.exceptions import ApplicationError, AuthorityError
from apps.fees import services
from apps.fees.models import FeeComment


def payment_comments_url(payment) -> str:
    return f"/api/v1/fees/payments/{payment.pk}/comments/"


def instalment_comments_url(instalment) -> str:
    return f"/api/v1/fees/instalments/{instalment.pk}/comments/"


@pytest.fixture
def plan(counsellor_user, enrollment):
    return services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount=Decimal("24000")
    )


@pytest.fixture
def payment(counsellor_user, plan):
    return services.record_payment(
        plan=plan, actor=counsellor_user, amount=Decimal("5000"), method="cash"
    )


@pytest.fixture
def instalment(plan):
    return plan.installments.order_by("sequence").first()


# ---------------------------------------------------------------------------
# Writing and reading one
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_counsellor_comments_on_a_payment_and_reads_it_back(
    api_client_no_csrf, counsellor_user, payment
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        payment_comments_url(payment),
        {"body": "Cheque with the bank since Tuesday; will chase Friday."},
        format="json",
    )
    assert response.status_code == 201, response.json()
    assert response.json()["author"] == "Kiran Counsellor"
    assert response.json()["body"] == "Cheque with the bank since Tuesday; will chase Friday."

    read = api_client_no_csrf.get(payment_comments_url(payment))
    assert read.status_code == 200
    assert [row["body"] for row in read.json()] == [
        "Cheque with the bank since Tuesday; will chase Friday."
    ]


@pytest.mark.django_db
def test_a_thread_reads_oldest_first(api_client_no_csrf, counsellor_user, payment):
    api_client_no_csrf.force_login(counsellor_user)
    for text in ("Rang the father.", "He asked for the 15th.", "Agreed, noted."):
        assert (
            api_client_no_csrf.post(
                payment_comments_url(payment), {"body": text}, format="json"
            ).status_code
            == 201
        )

    # A thread is a conversation: it reads downwards, unlike the lists
    # elsewhere in this app, which put the newest first.
    body = api_client_no_csrf.get(payment_comments_url(payment)).json()
    assert [row["body"] for row in body] == [
        "Rang the father.",
        "He asked for the 15th.",
        "Agreed, noted.",
    ]


@pytest.mark.django_db
def test_an_instalment_carries_its_own_thread(api_client_no_csrf, counsellor_user, instalment):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        instalment_comments_url(instalment),
        {"body": "Father asked to push this to the 15th; agreed."},
        format="json",
    )
    assert response.status_code == 201, response.json()

    read = api_client_no_csrf.get(instalment_comments_url(instalment))
    assert [row["body"] for row in read.json()] == [
        "Father asked to push this to the 15th; agreed."
    ]


@pytest.mark.django_db
def test_the_two_threads_do_not_mix(api_client_no_csrf, counsellor_user, payment, instalment):
    api_client_no_csrf.force_login(counsellor_user)
    api_client_no_csrf.post(payment_comments_url(payment), {"body": "About the money."}, "json")
    api_client_no_csrf.post(
        instalment_comments_url(instalment), {"body": "About the date."}, "json"
    )

    assert [
        row["body"] for row in api_client_no_csrf.get(payment_comments_url(payment)).json()
    ] == ["About the money."]
    assert [
        row["body"] for row in api_client_no_csrf.get(instalment_comments_url(instalment)).json()
    ] == ["About the date."]


# ---------------------------------------------------------------------------
# What a comment may be
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_empty_comment_is_refused(api_client_no_csrf, counsellor_user, payment):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(payment_comments_url(payment), {"body": "   "}, "json")
    assert response.status_code == 400
    assert FeeComment.objects.count() == 0


@pytest.mark.django_db
def test_a_comment_longer_than_the_field_is_refused(api_client_no_csrf, counsellor_user, payment):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(payment_comments_url(payment), {"body": "x" * 1001}, "json")
    assert response.status_code == 400
    assert FeeComment.objects.count() == 0


@pytest.mark.django_db
def test_a_comment_cannot_name_both_rows(counsellor_user, payment, instalment):
    # The database constraint says the same thing, but a caller that passed
    # both would hit it at commit — a 500 about a bug here instead of a 400
    # about the request.
    with pytest.raises(ApplicationError):
        services.add_comment(
            actor=counsellor_user, payment=payment, instalment=instalment, body="Both?"
        )
    assert FeeComment.objects.count() == 0


@pytest.mark.django_db
def test_a_comment_must_name_a_row(counsellor_user):
    with pytest.raises(ApplicationError):
        services.add_comment(actor=counsellor_user, body="About nothing in particular.")


@pytest.mark.django_db
def test_a_thread_cannot_be_edited_or_deleted(api_client_no_csrf, counsellor_user, payment):
    api_client_no_csrf.force_login(counsellor_user)
    api_client_no_csrf.post(payment_comments_url(payment), {"body": "As said at the time."}, "json")

    # A thread is a record of what was said at the time. There is no route
    # that changes one, so the methods a client might reach for are refused
    # by the endpoint itself.
    for method in (api_client_no_csrf.patch, api_client_no_csrf.put, api_client_no_csrf.delete):
        assert method(payment_comments_url(payment)).status_code == 405


# ---------------------------------------------------------------------------
# Who may read and who may write
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_student_cannot_read_or_write_a_comment(api_client_no_csrf, student, payment):
    api_client_no_csrf.force_login(student)
    assert api_client_no_csrf.get(payment_comments_url(payment)).status_code == 403
    assert (
        api_client_no_csrf.post(
            payment_comments_url(payment), {"body": "Mine?"}, "json"
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_a_students_own_fee_screen_never_shows_a_comment(
    api_client_no_csrf, counsellor_user, student_profile, payment
):
    api_client_no_csrf.force_login(counsellor_user)
    api_client_no_csrf.post(
        payment_comments_url(payment),
        {"body": "Says he will pay after the exam; chasing is pointless."},
        "json",
    )

    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.get("/api/v1/fees/me/")
    assert response.status_code == 200
    assert "chasing is pointless" not in response.content.decode()


@pytest.mark.django_db
def test_a_trainer_cannot_read_a_comment(api_client_no_csrf, trainer, payment):
    api_client_no_csrf.force_login(trainer)
    assert api_client_no_csrf.get(payment_comments_url(payment)).status_code == 403


@pytest.mark.django_db
def test_writing_needs_the_authority_that_records_payments(counsellor_user, student, payment):
    # Reading is `fee.view_any` and writing is `fee.manage_any`; the service
    # checks the second again, so hiding the composer on the screen stays a
    # courtesy rather than the control. No stock role holds the read
    # capability without the write one, so this exercises the service.
    with pytest.raises(AuthorityError):
        services.add_comment(actor=student, payment=payment, body="Let me in.")
    assert FeeComment.objects.count() == 0


@pytest.mark.django_db
def test_a_payment_at_another_centre_is_a_404(
    api_client_no_csrf, counsellor_user, unbounded_superadmin, other_branch_enrollment
):
    other_plan = services.set_fee_plan(
        enrollment=other_branch_enrollment,
        actor=unbounded_superadmin,
        agreed_amount=Decimal("24000"),
    )
    other_payment = services.record_payment(
        plan=other_plan, actor=unbounded_superadmin, amount=Decimal("5000"), method="cash"
    )

    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get(payment_comments_url(other_payment)).status_code == 404
    assert (
        api_client_no_csrf.post(
            payment_comments_url(other_payment), {"body": "Reaching over."}, "json"
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_an_instalment_at_another_centre_is_a_404(
    api_client_no_csrf, counsellor_user, unbounded_superadmin, other_branch_enrollment
):
    other_plan = services.set_fee_plan(
        enrollment=other_branch_enrollment,
        actor=unbounded_superadmin,
        agreed_amount=Decimal("24000"),
    )
    other_instalment = other_plan.installments.order_by("sequence").first()

    api_client_no_csrf.force_login(counsellor_user)
    assert api_client_no_csrf.get(instalment_comments_url(other_instalment)).status_code == 404


# ---------------------------------------------------------------------------
# What the screens read
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_fee_screen_shows_how_many_comments_each_row_has(
    api_client_no_csrf, counsellor_user, enrollment, payment, instalment
):
    api_client_no_csrf.force_login(counsellor_user)
    api_client_no_csrf.post(payment_comments_url(payment), {"body": "One."}, "json")
    api_client_no_csrf.post(payment_comments_url(payment), {"body": "Two."}, "json")
    api_client_no_csrf.post(instalment_comments_url(instalment), {"body": "Pushed."}, "json")

    body = api_client_no_csrf.get(f"/api/v1/fees/enrollments/{enrollment.pk}/").json()
    assert [row["comment_count"] for row in body["payments"]] == [2]

    rows = {row["sequence"]: row["comment_count"] for row in body["installments"]}
    assert rows[instalment.sequence] == 1
    assert all(count == 0 for sequence, count in rows.items() if sequence != instalment.sequence)


@pytest.mark.django_db
def test_the_counts_do_not_cost_a_query_per_row(
    api_client_no_csrf, counsellor_user, plan, enrollment, django_assert_max_num_queries
):
    for index in range(6):
        pay = services.record_payment(
            plan=plan,
            actor=counsellor_user,
            amount=Decimal("1000"),
            method="cash",
            paid_on=timezone.localdate() - timedelta(days=index),
        )
        services.add_comment(actor=counsellor_user, payment=pay, body=f"Note {index}.")

    api_client_no_csrf.force_login(counsellor_user)
    # Six payments and a six-row schedule: the counts are two grouped
    # queries, not twelve. The ceiling is loose on purpose — what this
    # catches is a count per row creeping back in.
    with django_assert_max_num_queries(25):
        response = api_client_no_csrf.get(f"/api/v1/fees/enrollments/{enrollment.pk}/")
    assert response.status_code == 200
    assert [row["comment_count"] for row in response.json()["payments"]] == [1] * 6


# ---------------------------------------------------------------------------
# The audit trail
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_audit_entry_names_the_row_and_not_the_text(counsellor_user, payment):
    services.add_comment(
        actor=counsellor_user,
        payment=payment,
        body="Mother is unwell; the family asked for a month.",
    )

    entry = AuditLog.objects.get(action=AuditAction.FEE_COMMENT_ADDED)
    assert entry.context["target"] == "payment"
    assert entry.context["payment_id"] == str(payment.pk)
    assert entry.context["receipt_number"] == payment.receipt_number
    assert entry.context["length"] == len("Mother is unwell; the family asked for a month.")
    # The audit trail is read far more widely than the fee screen, and a
    # comment can hold whatever a desk needs to say about a family.
    assert "unwell" not in str(entry.context)


@pytest.mark.django_db
def test_the_audit_entry_names_an_instalment_when_that_is_the_row(counsellor_user, instalment):
    services.add_comment(actor=counsellor_user, instalment=instalment, body="Pushed a fortnight.")

    entry = AuditLog.objects.get(action=AuditAction.FEE_COMMENT_ADDED)
    assert entry.context["target"] == "instalment"
    assert entry.context["instalment_id"] == str(instalment.pk)
    assert entry.context["instalment_sequence"] == instalment.sequence
    assert entry.context["payment_id"] is None


@pytest.mark.django_db
def test_a_comment_moves_no_money(counsellor_user, plan, payment):
    before = (plan.payable, plan.paid, plan.balance)
    services.add_comment(actor=counsellor_user, payment=payment, body="Still waiting.")

    plan.refresh_from_db()
    fresh = type(plan).objects.with_totals().get(pk=plan.pk)
    assert (fresh.payable, fresh.paid, fresh.balance) == before
