"""The admission record: one student signing up for one or more courses.

What this suite is for, in order of how expensive the mistake would be:

1. **The discount splits exactly.** ₹2,000 across ₹20,000 and ₹15,000 does not
   divide into paise, and a split that loses one makes the fee ledger
   un-reconcilable for the rest of the year. Every case here sums the parts
   back to the whole.
2. The admission groups without *moving* money: a course line's charge is
   still that course's, an additional fee is charged on a named course line,
   and nothing is held centrally.
3. It is scoped like everything else — a student you cannot see is a student
   you cannot admit.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.admissions import services
from apps.admissions.models import Admission, AdmissionLine, DiscountKind, LineKind
from apps.common.exceptions import ApplicationError, AuthorityError

pytestmark = pytest.mark.django_db

D = Decimal


# ---------------------------------------------------------------------------
# The split
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "totals,discount",
    [
        ([D("20000"), D("15000")], D("2000")),  # the awkward one: 1142.857…
        ([D("10000"), D("10000"), D("10000")], D("100")),  # 33.33 three ways
        ([D("30000")], D("4999.99")),
        ([D("1"), D("1"), D("1")], D("1")),  # a rupee across three lines
        ([D("12345.67"), D("7654.33")], D("3333.33")),
        ([D("20000"), D("15000")], D("0")),
    ],
)
def test_a_discount_split_across_lines_adds_back_to_exactly_itself(totals, discount):
    shares = services.split_discount(totals, discount)
    assert sum(shares) == discount
    assert all(share >= 0 for share in shares)
    assert len(shares) == len(totals)


def test_the_split_is_proportional_not_equal():
    """A bigger course carries more of the discount. An equal split would
    quietly move money between two courses' ledgers."""
    shares = services.split_discount([D("30000"), D("10000")], D("4000"))
    assert shares == [D("3000.00"), D("1000.00")]


def test_a_discount_larger_than_the_fee_is_capped_at_it():
    """An institute can waive a fee. It cannot end up owing money for having
    agreed to waive one."""
    shares = services.split_discount([D("5000")], D("9000"))
    assert sum(shares) == D("5000")


def test_the_same_inputs_always_split_the_same_way():
    """Ties go to the earlier line, so two runs of the same admission can
    never produce two different ledgers."""
    first = services.split_discount([D("1000"), D("1000"), D("1000")], D("10.01"))
    second = services.split_discount([D("1000"), D("1000"), D("1000")], D("10.01"))
    assert first == second
    assert sum(first) == D("10.01")


def test_a_percentage_discount_becomes_rupees_once():
    assert services.discount_amount_for(D("30000"), kind=DiscountKind.PERCENT, value=10) == D(
        "3000.00"
    )
    with pytest.raises(ApplicationError):
        services.discount_amount_for(D("30000"), kind=DiscountKind.PERCENT, value=101)


# ---------------------------------------------------------------------------
# Recording one
# ---------------------------------------------------------------------------


def _course(admin_user, title: str, category):
    from apps.courses import services as course_services

    return course_services.create_course(
        actor=admin_user,
        title=title,
        category=category,
        short_description="A course.",
        description="Full description.",
        learning_objectives=["Learn it"],
    )


def test_an_admission_records_every_course_its_total_and_the_split(
    admin_user, student_profile, published_course, category
):
    other = _course(admin_user, "Data Analytics", category)
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[
            {"kind": "course", "course": published_course, "unit_fee": "20000"},
            {"kind": "course", "course": other, "unit_fee": "15000"},
        ],
        discount_kind=DiscountKind.FLAT,
        discount_value="2000",
        note="Agreed with the father.",
    )

    assert admission.gross_total == D("35000.00")
    assert admission.total_fees == D("33000.00")
    lines = list(admission.lines.order_by("created_at"))
    assert [line.course_id for line in lines] == [published_course.pk, other.pk]
    assert sum(line.discount_share for line in lines) == D("2000.00")
    # Proportional, and the bigger course carries more of it.
    assert lines[0].discount_share > lines[1].discount_share


def test_quantity_multiplies_the_agreed_fee(admin_user, student_profile, published_course):
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "quantity": 3, "unit_fee": "5000"}],
    )
    assert admission.gross_total == D("15000.00")
    assert admission.lines.get().line_total == D("15000.00")


def test_an_additional_fee_is_charged_on_a_course_line(
    admin_user, student_profile, published_course
):
    """It has to belong to a course: a fee with no course has no enrolment,
    and an enrolment is what a fee plan hangs off."""
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[
            {"kind": "course", "course": published_course, "unit_fee": "30000"},
            {"kind": "additional_fee", "label": "Exam fee", "unit_fee": "2000"},
        ],
    )

    course_line = admission.lines.get(kind=LineKind.COURSE)
    extra = admission.lines.get(kind=LineKind.ADDITIONAL_FEE)
    assert extra.charged_on_id == course_line.pk
    assert extra.course_id is None
    # The plan for that course is agreed at the course plus its extras.
    assert services.charge_for(course_line) == D("32000.00")
    assert admission.gross_total == D("32000.00")


def test_an_additional_fee_can_name_which_course_it_belongs_to(
    admin_user, student_profile, published_course, category
):
    other = _course(admin_user, "Linux", category)
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[
            {"kind": "course", "course": published_course, "unit_fee": "20000"},
            {"kind": "course", "course": other, "unit_fee": "15000"},
            {"kind": "additional_fee", "label": "Kit", "unit_fee": "1000", "charged_on": 1},
        ],
    )
    extra = admission.lines.get(kind=LineKind.ADDITIONAL_FEE)
    assert extra.charged_on.course_id == other.pk


def test_an_additional_fee_cannot_be_charged_on_another_additional_fee(
    admin_user, student_profile, published_course
):
    with pytest.raises(ApplicationError):
        services.create_admission(
            actor=admin_user,
            student=student_profile,
            lines=[
                {"kind": "course", "course": published_course, "unit_fee": "20000"},
                {"kind": "additional_fee", "label": "Kit", "unit_fee": "1000"},
                {"kind": "additional_fee", "label": "Exam", "unit_fee": "500", "charged_on": 1},
            ],
        )
    assert Admission.objects.count() == 0


def test_the_discount_is_split_over_courses_only_never_the_extras(
    admin_user, student_profile, published_course
):
    """An additional fee is charged on a course line, so discounting it
    separately would take the same rupees off twice."""
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[
            {"kind": "course", "course": published_course, "unit_fee": "30000"},
            {"kind": "additional_fee", "label": "Exam fee", "unit_fee": "2000"},
        ],
        discount_value="1000",
    )
    extra = admission.lines.get(kind=LineKind.ADDITIONAL_FEE)
    course_line = admission.lines.get(kind=LineKind.COURSE)
    assert extra.discount_share == D("0.00")
    assert course_line.discount_share == D("1000.00")


def test_an_admission_needs_a_course_and_a_fee_needs_a_name(
    admin_user, student_profile, published_course
):
    with pytest.raises(ApplicationError):
        services.create_admission(actor=admin_user, student=student_profile, lines=[])
    with pytest.raises(ApplicationError):
        services.create_admission(
            actor=admin_user,
            student=student_profile,
            lines=[{"kind": "additional_fee", "label": "Exam", "unit_fee": "500"}],
        )
    with pytest.raises(ApplicationError):
        services.create_admission(
            actor=admin_user,
            student=student_profile,
            lines=[
                {"kind": "course", "course": published_course, "unit_fee": "100"},
                {"kind": "additional_fee", "label": "   ", "unit_fee": "500"},
            ],
        )
    assert Admission.objects.count() == 0
    assert AdmissionLine.objects.count() == 0


def test_a_closed_academic_year_takes_no_new_admission(
    admin_user, student_profile, published_course
):
    from apps.organisation.models import AcademicYear

    closed = AcademicYear.objects.create(name="2019", is_closed=True)
    with pytest.raises(ApplicationError):
        services.create_admission(
            actor=admin_user,
            student=student_profile,
            lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
            academic_year=closed,
        )


def test_the_admission_is_filed_under_the_students_own_centre(
    admin_user, student_profile, published_course
):
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
    )
    assert admission.branch_id == student_profile.branch_id


def test_a_student_at_another_centre_cannot_be_admitted(
    other_branch_manager, student_profile, published_course
):
    with pytest.raises(AuthorityError):
        services.create_admission(
            actor=other_branch_manager,
            student=student_profile,
            lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
        )
    assert Admission.objects.count() == 0


def test_recording_an_admission_is_audited_durably(admin_user, student_profile, published_course):
    from apps.audit.models import AuditLog

    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
    )
    row = AuditLog.objects.get(resource_type="admission", resource_id=str(admission.pk))
    assert row.action == "admission.created"


# ---------------------------------------------------------------------------
# Cancelling one
# ---------------------------------------------------------------------------


def test_cancelling_an_admission_settles_each_courses_money(
    admin_user, student_profile, published_course, batch, enrollment
):
    from apps.fees import services as fee_services
    from apps.fees.models import FeePlan

    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "20000"}],
    )
    line = admission.lines.get()
    services.attach_enrollment(actor=admin_user, line=line, enrollment=enrollment)
    fee_services.set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="20000")

    services.cancel_admission(actor=admin_user, admission=admission, reason="Moved city.")

    admission.refresh_from_db()
    assert admission.is_cancelled
    assert admission.cancellation_reason == "Moved city."
    plan = FeePlan.objects.get(enrollment=enrollment)
    assert plan.is_cancelled
    # Nothing was paid, so the whole fee is written off rather than left owed
    # by nobody — the ledger's own rule, reused rather than reimplemented.
    assert plan.written_off == Decimal("20000.00")


def test_an_admission_with_no_seat_yet_still_cancels(admin_user, student_profile, published_course):
    """The agreement exists before the batch does. Cancelling it must not
    require an enrolment that was never made."""
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
    )
    services.cancel_admission(actor=admin_user, admission=admission, reason="Changed mind.")
    admission.refresh_from_db()
    assert admission.is_cancelled


def test_cancelling_needs_a_reason_and_happens_once(admin_user, student_profile, published_course):
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
    )
    with pytest.raises(ApplicationError):
        services.cancel_admission(actor=admin_user, admission=admission, reason="  ")
    services.cancel_admission(actor=admin_user, admission=admission, reason="Changed mind.")
    with pytest.raises(ApplicationError):
        services.cancel_admission(actor=admin_user, admission=admission, reason="Again.")


def test_an_enrolment_from_another_student_cannot_be_attached(
    admin_user, student_profile, published_course, other_enrollment
):
    admission = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
    )
    with pytest.raises(ApplicationError):
        services.attach_enrollment(
            actor=admin_user, line=admission.lines.get(), enrollment=other_enrollment
        )


def test_the_admission_date_defaults_to_today_and_can_be_set(
    admin_user, student_profile, published_course
):
    backdated = services.create_admission(
        actor=admin_user,
        student=student_profile,
        lines=[{"kind": "course", "course": published_course, "unit_fee": "100"}],
        admission_date=date(2026, 10, 1),
    )
    assert backdated.admission_date == date(2026, 10, 1)
