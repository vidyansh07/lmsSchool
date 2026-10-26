"""A report somebody builds themselves.

The twenty fixed reports answer the questions somebody thought of in advance.
This answers the rest — "RHCSA and AWS payments at Jaipur between April and
June, by course, with what was collected against each" — and the whole risk
of that is handing a caller the ORM.

So what is pinned here is mostly what it *refuses*:

- a column, a filter field, an operator or a measure that the dataset does
  not declare, however correctly it is spelled;
- reaching a relation nobody declared, which is the password-oracle shape
  `apps.common.filtering` already argues about at length;
- and, as much as the rows, the *totals*: a count is a disclosure, so a group
  containing only rows the caller cannot see does not appear at all.

Plus the two things a report has to be honest about: that it was cut at the
row limit, and that a grouped answer is a different shape from a list.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.exceptions import ApplicationError
from apps.fees import services as fee_services
from apps.reporting import builder, datasets

pytestmark = pytest.mark.django_db

BUILD = "/api/v1/reports/build/"
CATALOGUE = "/api/v1/reports/datasets/"


# ---------------------------------------------------------------------------
# What it will not do
# ---------------------------------------------------------------------------


def test_an_undeclared_column_is_refused(admin_user):
    from apps.students import access as students_access

    with pytest.raises(ApplicationError):
        builder.run(
            dataset=datasets.STUDENTS,
            rows=students_access.visible_students(admin_user),
            columns=["user__password"],
        )


def test_an_undeclared_filter_field_is_refused(admin_user):
    from apps.students import access as students_access

    # The shape the allowlist exists for: a relation walk nobody declared.
    with pytest.raises(ApplicationError):
        builder.run(
            dataset=datasets.STUDENTS,
            rows=students_access.visible_students(admin_user),
            filters=[{"field": "user__password", "op": "istartswith", "value": "a"}],
        )


def test_an_operator_the_field_does_not_offer_is_refused(admin_user):
    from apps.students import access as students_access

    # `city` is text; `gt` belongs to numbers and dates. Refused by name
    # rather than silently returning nothing, because an empty report reads
    # as fact.
    with pytest.raises(ApplicationError):
        builder.run(
            dataset=datasets.STUDENTS,
            rows=students_access.visible_students(admin_user),
            filters=[{"field": "city", "op": "gt", "value": "Jaipur"}],
        )


def test_an_undeclared_measure_is_refused(admin_user):
    from apps.students import access as students_access

    with pytest.raises(ApplicationError):
        builder.run(
            dataset=datasets.STUDENTS,
            rows=students_access.visible_students(admin_user),
            group_by="city",
            measures=["sum_of_everything"],
        )


def test_in_without_a_list_is_refused(admin_user):
    from apps.students import access as students_access

    with pytest.raises(ApplicationError):
        builder.run(
            dataset=datasets.STUDENTS,
            rows=students_access.visible_students(admin_user),
            filters=[{"field": "branch", "op": "in", "value": "not-a-list"}],
        )


# ---------------------------------------------------------------------------
# What it does
# ---------------------------------------------------------------------------


def test_it_returns_the_columns_asked_for_and_no_others(admin_user, student_profile):
    from apps.students import access as students_access

    result = builder.run(
        dataset=datasets.STUDENTS,
        rows=students_access.visible_students(admin_user),
        columns=["student_id", "name"],
    )

    assert [column["name"] for column in result["columns"]] == ["student_id", "name"]
    assert set(result["rows"][0]) == {"student_id", "name"}
    # The public name comes back, never the ORM path it was read through.
    assert "user__full_name" not in result["rows"][0]


def test_a_filter_narrows(admin_user, student_profile):
    from apps.students import access as students_access

    rows = students_access.visible_students(admin_user)
    everyone = builder.run(dataset=datasets.STUDENTS, rows=rows, columns=["student_id"])
    nobody = builder.run(
        dataset=datasets.STUDENTS,
        rows=rows,
        columns=["student_id"],
        filters=[{"field": "city", "op": "exact", "value": "Nowhere"}],
    )

    assert len(everyone["rows"]) >= 1
    assert nobody["rows"] == []


def test_grouping_totals_the_money(admin_user, counsellor_user, enrollment):
    from apps.batches import access as batch_access
    from apps.fees.models import FeePayment

    plan = fee_services.set_fee_plan(
        enrollment=enrollment, actor=counsellor_user, agreed_amount=Decimal("24000")
    )
    fee_services.record_payment(
        plan=plan, actor=counsellor_user, amount=Decimal("5000"), method="cash"
    )
    fee_services.record_payment(
        plan=plan, actor=counsellor_user, amount=Decimal("3000"), method="upi"
    )

    result = builder.run(
        dataset=datasets.FEE_PAYMENTS,
        rows=FeePayment.objects.filter(
            plan__enrollment__in=batch_access.visible_enrollments(admin_user)
        ),
        group_by="course",
        measures=["count", "total"],
    )

    assert result["grouped"] is True
    assert result["rows"][0]["count"] == 2
    assert result["rows"][0]["total"] == Decimal("8000")


def test_a_grouped_answer_says_it_is_grouped(admin_user, student_profile):
    from apps.students import access as students_access

    rows = students_access.visible_students(admin_user)
    flat = builder.run(dataset=datasets.STUDENTS, rows=rows, columns=["student_id"])
    grouped = builder.run(dataset=datasets.STUDENTS, rows=rows, group_by="city")

    # One per group with totals is a different shape from a list of records;
    # saying so beats letting a reader infer it from the columns.
    assert flat["grouped"] is False
    assert grouped["grouped"] is True


def test_it_says_when_it_was_cut(admin_user, student_profile):
    from apps.students import access as students_access

    result = builder.run(
        dataset=datasets.STUDENTS,
        rows=students_access.visible_students(admin_user),
        columns=["student_id"],
        limit=0,
    )

    # A report that silently stops is a report somebody reads as the whole
    # truth.
    assert result["truncated"] is True
    assert result["rows"] == []


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_a_report_cannot_reach_another_centre(
    api_client_no_csrf, counsellor_user, student_profile, other_branch_student
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        BUILD, {"dataset": "students", "columns": ["student_id"]}, format="json"
    )

    assert response.status_code == 200, response.json()
    ids = {row["student_id"] for row in response.json()["rows"]}
    assert student_profile.student_id in ids
    # The rows start from the caller's own visible set, so no filter -- and
    # no absence of one -- can widen it.
    assert other_branch_student.student_id not in ids


def test_a_group_with_no_visible_rows_does_not_appear(
    api_client_no_csrf, counsellor_user, student_profile, other_branch_student
):
    api_client_no_csrf.force_login(counsellor_user)
    response = api_client_no_csrf.post(
        BUILD, {"dataset": "students", "group_by": "centre"}, format="json"
    )

    assert response.status_code == 200, response.json()
    centres = {row["centre"] for row in response.json()["rows"]}
    # A count is as much a disclosure as a row: "1 student at Pune" says Pune
    # students exist.
    assert len(centres) == 1


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------


def test_the_catalogue_lists_what_can_be_built(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.get(CATALOGUE)

    assert response.status_code == 200
    body = response.json()
    assert {row["key"] for row in body} >= {"students", "fee_payments", "enrolments"}
    payments = next(row for row in body if row["key"] == "fee_payments")
    assert {m["name"] for m in payments["measures"]} == {"count", "total"}


def test_the_catalogue_never_leaks_an_orm_path(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    body = api_client_no_csrf.get(CATALOGUE).json()

    # A caller asks for `course`; `plan__enrollment__batch__course__title` is
    # the server's business, and keeping it there is what stops a field
    # becoming reachable by being spelled correctly.
    assert "__" not in str(body)


def test_a_student_cannot_build_a_report(api_client_no_csrf, student_profile):
    api_client_no_csrf.force_login(student_profile.user)
    response = api_client_no_csrf.post(
        BUILD, {"dataset": "students", "columns": ["student_id"]}, format="json"
    )
    assert response.status_code == 403


def test_an_unknown_dataset_is_refused(api_client_no_csrf, admin_user):
    api_client_no_csrf.force_login(admin_user)
    response = api_client_no_csrf.post(BUILD, {"dataset": "payroll"}, format="json")
    assert response.status_code == 400
