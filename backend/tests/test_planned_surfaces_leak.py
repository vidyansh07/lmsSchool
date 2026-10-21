"""The surfaces the next features will be built on, probed for leaks first.

Each planned feature reuses something that already exists rather than adding a
new entity — a student's own fee receipts, enquiry follow-ups as activities,
feedback as an activity a student may read. That is the right shape, and it
means the leak question is not "is the new code safe" but "is the thing I am
about to build on already tight". These answer that before any of it is
written, because a leak inherited from a foundation is the hardest kind to
notice afterwards.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.fees.services import record_payment, set_fee_plan

pytestmark = pytest.mark.django_db

FEE = Decimal("20000.00")


@pytest.fixture
def paid_enrollment(enrollment, admin_user):
    plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount=FEE)
    payment = record_payment(plan=plan, actor=admin_user, amount="5000")
    return plan, payment


class TestAStudentsOwnMoney:
    """Feature: the student dashboard showing payments, dues and receipts."""

    def test_a_student_reads_their_own_fees(
        self, api_client_no_csrf, paid_enrollment, enrollment
    ):
        api_client_no_csrf.force_authenticate(user=enrollment.student.user)

        response = api_client_no_csrf.get("/api/v1/fees/me/")

        assert response.status_code == 200

    def test_a_student_cannot_read_another_students_fees(
        self, api_client_no_csrf, paid_enrollment, other_student_profile
    ):
        api_client_no_csrf.force_authenticate(user=other_student_profile.user)

        response = api_client_no_csrf.get("/api/v1/fees/me/")

        # `me/` resolves from the session, so the worst case is an empty
        # summary — never somebody else's.
        assert response.status_code in (200, 404)
        assert str(FEE) not in str(response.data)

    def test_a_student_cannot_pull_another_students_receipt(
        self, api_client_no_csrf, paid_enrollment, other_student_profile
    ):
        # The receipt is a PDF of somebody's name, course and money. If an id
        # is enough to fetch one, every receipt in the institute is readable.
        _plan, payment = paid_enrollment
        api_client_no_csrf.force_authenticate(user=other_student_profile.user)

        response = api_client_no_csrf.get(f"/api/v1/fees/payments/{payment.pk}/receipt/")

        assert response.status_code in (403, 404), "a student fetched a stranger's receipt"

    def test_a_student_cannot_record_a_payment_against_themselves(
        self, api_client_no_csrf, enrollment
    ):
        # The dashboard shows what is owed. It must not become a way to say it
        # was paid.
        api_client_no_csrf.force_authenticate(user=enrollment.student.user)

        response = api_client_no_csrf.post(
            f"/api/v1/fees/enrollments/{enrollment.pk}/payments/",
            {"amount": "20000"},
            format="json",
        )

        assert response.status_code in (403, 404)

    def test_a_student_cannot_refund_themselves(
        self, api_client_no_csrf, paid_enrollment, enrollment
    ):
        _plan, payment = paid_enrollment
        api_client_no_csrf.force_authenticate(user=enrollment.student.user)

        response = api_client_no_csrf.post(
            f"/api/v1/fees/payments/{payment.pk}/refund/",
            {"reason": "give it back"},
            format="json",
        )

        assert response.status_code in (403, 404)


class TestActivitiesAsFollowUpsAndFeedback:
    """Features: the enquiry follow-up thread, and feedback a student may read."""

    def test_a_student_sees_only_activities_marked_visible_to_them(
        self, api_client_no_csrf, enrollment, admin_user
    ):
        # Two gates, not one: the activity *type* must be student-visible and
        # the instance must be too. Feedback is built on this, so an internal
        # note must not become readable by flipping one flag.
        from apps.work.access import student_visible_activities

        queryset = student_visible_activities(enrollment.student)
        sql = str(queryset.query)
        assert "visible_to_student" in sql
        assert "student_visible" in sql

    def test_an_enquiry_activity_can_never_reach_a_student(
        self, api_client_no_csrf, enrollment
    ):
        # An enquiry activity has no student on it at all, and the student
        # surface filters by student — so a counsellor's notes on a lead
        # cannot surface on anybody's dashboard.
        from apps.work.access import student_visible_activities

        assert "student_id" in str(student_visible_activities(enrollment.student).query)

    def test_a_student_cannot_read_the_staff_activity_list(
        self, api_client_no_csrf, enrollment
    ):
        api_client_no_csrf.force_authenticate(user=enrollment.student.user)

        response = api_client_no_csrf.get("/api/v1/activities/")

        assert response.status_code in (403, 404) or response.data.get("count") == 0


class TestCancellingAnAdmission:
    """Feature: cancel an admission, then refund.

    These record what the system does *today*, so the change is made with the
    current behaviour written down rather than assumed.
    """

    def test_cancelling_stops_the_chasing(self, paid_enrollment, enrollment, admin_user):
        """A cancelled admission is not chased for the money.

        The overdue warning filters live statuses, and cancelled is not one.
        Asserted against a plan that *is* overdue, so the test fails if that
        filter is ever dropped rather than passing because nothing was due.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.enrollments.models import EnrollmentStatus
        from apps.enrollments.services import set_enrollment_status
        from apps.warnings.services import warnings_for

        plan, _payment = paid_enrollment
        plan.next_due_on = timezone.localdate() - timedelta(days=7)
        plan.save(update_fields=["next_due_on"])

        before = {warning["kind"] for warning in warnings_for(admin_user)}
        assert "fees_overdue" in before, "the fixture is not actually overdue"

        set_enrollment_status(
            enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user
        )

        after = {warning["kind"] for warning in warnings_for(admin_user)}
        assert "fees_overdue" not in after

    def test_but_cancelling_leaves_the_fee_standing(
        self, paid_enrollment, enrollment, admin_user
    ):
        """The gap the cancellation feature has to close.

        Cancelling the enrolment does not touch the fee plan: the student still
        owes the full amount on their record and in every list, while no
        warning fires about it. Whatever cancellation ends up doing — waiving
        the balance, applying a charge, refunding the rest — it has to say so
        explicitly, because nothing happens by itself.
        """
        from apps.enrollments.models import EnrollmentStatus
        from apps.enrollments.services import set_enrollment_status

        plan, _payment = paid_enrollment
        set_enrollment_status(
            enrollment=enrollment, target=EnrollmentStatus.CANCELLED, actor=admin_user
        )

        plan.refresh_from_db()
        assert plan.payable == FEE
        assert plan.balance == FEE - Decimal("5000.00")
