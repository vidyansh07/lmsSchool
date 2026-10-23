"""A course's own instalment structure, and deleting a course.

Two things ClassPro's course screen does that this ERP could not:

* **"Add Fee Instalment Structure"** — the course says how its fee is
  normally collected, so a counsellor does not retype "half now, the rest at
  thirty days" at every admission. The structure is a *template*: it is copied
  into the fee plan the day the plan is made and never read back, so changing
  it cannot move a due date for anybody already enrolled.
* **Delete** — for the course created by mistake. Refused the moment anybody
  has been taught under it; archiving is what that case wants.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.exceptions import ApplicationError, ConflictError
from apps.courses import services
from apps.courses.models import CourseFeeInstalment

pytestmark = pytest.mark.django_db


def _client(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _rows(*pairs) -> list[dict]:
    return [{"percent": percent, "due_after_days": days} for percent, days in pairs]


# ---------------------------------------------------------------------------
# The structure itself
# ---------------------------------------------------------------------------


def test_the_structure_is_replaced_as_a_set(admin_user, published_course):
    services.set_fee_instalments(
        course=published_course,
        actor=admin_user,
        rows=_rows((50, 0), (50, 30)),
    )
    assert published_course.fee_instalments.count() == 2

    services.set_fee_instalments(
        course=published_course,
        actor=admin_user,
        rows=_rows((100, 0)),
    )
    rows = list(published_course.fee_instalments.all())
    assert [row.sequence for row in rows] == [1]
    assert rows[0].percent == Decimal("100.00")


def test_an_empty_structure_is_an_answer(admin_user, published_course):
    """ "Collect it however each admission decides" is a real choice, and it is
    what every course says until somebody sets a structure up."""
    services.set_fee_instalments(course=published_course, actor=admin_user, rows=_rows((100, 0)))
    services.set_fee_instalments(course=published_course, actor=admin_user, rows=[])
    assert published_course.fee_instalments.count() == 0


def test_the_shares_must_add_up_to_a_hundred(admin_user, published_course):
    with pytest.raises(ApplicationError) as refused:
        services.set_fee_instalments(
            course=published_course, actor=admin_user, rows=_rows((40, 0), (40, 30))
        )
    assert "80" in str(refused.value.detail)
    assert published_course.fee_instalments.count() == 0


def test_a_zero_share_is_not_an_instalment(admin_user, published_course):
    with pytest.raises(ApplicationError):
        services.set_fee_instalments(
            course=published_course, actor=admin_user, rows=_rows((100, 0), (0, 30))
        )


def test_an_instalment_cannot_fall_before_the_admission(admin_user, published_course):
    with pytest.raises(ApplicationError):
        services.set_fee_instalments(
            course=published_course, actor=admin_user, rows=_rows((100, -5))
        )


def test_too_many_instalments_are_refused(admin_user, published_course):
    """The ledger caps a plan's schedule at 36, so a 40-row template would be
    a structure that could never be applied."""
    with pytest.raises(ApplicationError):
        services.set_fee_instalments(
            course=published_course,
            actor=admin_user,
            rows=_rows(*[(Decimal("2.50"), index * 30) for index in range(40)]),
        )


def test_setting_the_structure_is_audited(admin_user, published_course):
    from apps.audit.models import AuditAction, AuditLog

    services.set_fee_instalments(
        course=published_course, actor=admin_user, rows=_rows((60, 0), (40, 45))
    )
    entry = AuditLog.objects.filter(action=AuditAction.COURSE_FEE_SCHEDULE_SET).get()
    assert entry.context["code"] == published_course.code
    assert [row["due_after_days"] for row in entry.context["instalments"]] == [0, 45]


# ---------------------------------------------------------------------------
# What a fee plan does with it
# ---------------------------------------------------------------------------


def test_a_new_plan_takes_the_courses_structure(admin_user, published_course, enrollment):
    from apps.fees.services import set_fee_plan

    services.set_fee_instalments(
        course=published_course, actor=admin_user, rows=_rows((50, 0), (25, 30), (25, 60))
    )
    plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="20000")

    today = timezone.localdate()
    rows = list(plan.installments.all())
    assert [row.amount for row in rows] == [
        Decimal("10000.00"),
        Decimal("5000.00"),
        Decimal("5000.00"),
    ]
    assert [row.due_on for row in rows] == [
        today,
        today + timedelta(days=30),
        today + timedelta(days=60),
    ]


def test_the_structure_is_applied_to_what_is_payable_not_the_full_fee(
    admin_user, published_course, enrollment
):
    """A 10% discount does not make the first instalment 10% of a fee nobody
    owes. The shares are of `payable`, which is the whole reason the template
    keeps percentages instead of rupees."""
    from apps.fees.services import set_fee_plan

    services.set_fee_instalments(
        course=published_course, actor=admin_user, rows=_rows((50, 0), (50, 30))
    )
    plan = set_fee_plan(
        enrollment=enrollment,
        actor=admin_user,
        agreed_amount="20000",
        discount_amount="2000",
        discount_reason="Early bird",
    )
    assert [row.amount for row in plan.installments.all()] == [
        Decimal("9000.00"),
        Decimal("9000.00"),
    ]


def test_the_odd_paisa_lands_on_the_first_instalment(admin_user, published_course, enrollment):
    """Thirds of ₹9,999 do not divide, and rounding each share down leaves 72
    paise unscheduled. The schedule must still sum to exactly the payable
    fee, so the leftover lands on the first instalment."""
    from apps.fees.services import set_fee_plan

    services.set_fee_instalments(
        course=published_course,
        actor=admin_user,
        rows=_rows((Decimal("33.33"), 0), (Decimal("33.33"), 30), (Decimal("33.34"), 60)),
    )
    plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="9999")

    amounts = [row.amount for row in plan.installments.all()]
    assert sum(amounts) == plan.payable
    assert amounts[0] > amounts[1]


def test_changing_the_structure_leaves_existing_plans_alone(
    admin_user, published_course, enrollment
):
    """The snapshot rule `CoursePrice` follows. A student on a two-instalment
    plan does not wake up on a six-instalment one."""
    from apps.fees.services import set_fee_plan

    services.set_fee_instalments(
        course=published_course, actor=admin_user, rows=_rows((50, 0), (50, 30))
    )
    plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="20000")
    before = [(row.amount, row.due_on) for row in plan.installments.all()]

    services.set_fee_instalments(
        course=published_course, actor=admin_user, rows=_rows((25, 0), (25, 30), (50, 90))
    )
    plan.refresh_from_db()
    assert [(row.amount, row.due_on) for row in plan.installments.all()] == before


def test_a_course_with_no_structure_still_gets_the_even_split(
    admin_user, published_course, enrollment
):
    from apps.fees.models import DEFAULT_INSTALLMENT_COUNT
    from apps.fees.services import set_fee_plan

    plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="12000")
    assert plan.installments.count() == DEFAULT_INSTALLMENT_COUNT


def test_a_schedule_asked_for_explicitly_beats_the_structure(
    admin_user, published_course, enrollment
):
    """The counsellor is in front of the student; the template is not."""
    from apps.fees.services import set_fee_plan

    services.set_fee_instalments(
        course=published_course, actor=admin_user, rows=_rows((50, 0), (50, 30))
    )
    plan = set_fee_plan(
        enrollment=enrollment,
        actor=admin_user,
        agreed_amount="20000",
        installments=[{"amount": "20000", "due_on": timezone.localdate()}],
    )
    assert plan.installments.count() == 1


def test_nothing_to_collect_is_an_empty_schedule(admin_user, published_course, enrollment):
    from apps.fees.services import set_fee_plan

    services.set_fee_instalments(course=published_course, actor=admin_user, rows=_rows((100, 0)))
    plan = set_fee_plan(enrollment=enrollment, actor=admin_user, agreed_amount="0")
    assert plan.installments.count() == 0


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


def _url(course) -> str:
    return f"/api/v1/courses/{course.pk}/instalments/"


def test_the_api_reads_and_replaces_the_structure(api_client_no_csrf, admin_user, published_course):
    client = _client(admin_user)
    saved = client.put(
        _url(published_course),
        {
            "instalments": [
                {"label": "Admission", "percent": "60", "due_after_days": 0},
                {"label": "Balance", "percent": "40", "due_after_days": 30},
            ]
        },
        format="json",
    )
    assert saved.status_code == 200, saved.content
    assert [row["label"] for row in saved.json()] == ["Admission", "Balance"]
    assert [row["sequence"] for row in saved.json()] == [1, 2]

    read = client.get(_url(published_course))
    assert [row["percent"] for row in read.json()] == ["60.00", "40.00"]


def test_the_api_refuses_a_structure_that_does_not_add_up(
    api_client_no_csrf, admin_user, published_course
):
    response = _client(admin_user).put(
        _url(published_course),
        {"instalments": [{"percent": "30", "due_after_days": 0}]},
        format="json",
    )
    assert response.status_code == 400
    assert not CourseFeeInstalment.objects.exists()


def test_an_unknown_field_is_refused_rather_than_dropped(
    api_client_no_csrf, admin_user, published_course
):
    response = _client(admin_user).put(
        _url(published_course),
        {"instalments": [{"percent": "100", "sequence": 7}]},
        format="json",
    )
    assert response.status_code == 400


def test_a_student_reads_the_structure_and_changes_none(
    api_client_no_csrf, admin_user, published_course, student_profile, enrollment
):
    """A student may see how their course's fee is collected. Setting it is
    the institute's business."""
    services.set_fee_instalments(course=published_course, actor=admin_user, rows=_rows((100, 0)))
    client = _client(student_profile.user)

    assert client.get(_url(published_course)).status_code == 200
    refused = client.put(_url(published_course), {"instalments": []}, format="json")
    assert refused.status_code == 403
    assert published_course.fee_instalments.count() == 1


def test_a_trainer_who_does_not_teach_the_course_cannot_set_it(
    api_client_no_csrf, trainer, draft_course
):
    response = _client(trainer).put(_url(draft_course), {"instalments": []}, format="json")
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Deleting a course
# ---------------------------------------------------------------------------


def test_an_administrator_deletes_a_course_nobody_studied(
    api_client_no_csrf, admin_user, draft_course
):
    from apps.audit.models import AuditAction, AuditLog
    from apps.courses.models import Course

    code = draft_course.code
    response = _client(admin_user).delete(f"/api/v1/courses/{draft_course.pk}/")

    assert response.status_code == 204, response.content
    assert not Course.objects.filter(pk=draft_course.pk).exists()
    assert AuditLog.objects.filter(action=AuditAction.COURSE_DELETED).get().context["code"] == code


def test_a_manager_may_archive_but_not_delete(api_client_no_csrf, manager_user, draft_course):
    """Archiving is the ordinary end of a course's life; destroying one is the
    administrator's."""
    from apps.courses.models import Course

    response = _client(manager_user).delete(f"/api/v1/courses/{draft_course.pk}/")
    assert response.status_code == 403
    assert Course.objects.filter(pk=draft_course.pk).exists()


def test_a_course_with_batches_is_refused(admin_user, published_course, batch):
    with pytest.raises(ConflictError) as refused:
        services.delete_course(course=published_course, actor=admin_user)
    assert "batch" in str(refused.value.detail)


def test_the_refusal_says_to_archive_instead(
    api_client_no_csrf, admin_user, published_course, enrollment
):
    from apps.courses.models import Course

    response = _client(admin_user).delete(f"/api/v1/courses/{published_course.pk}/")
    assert response.status_code == 409
    assert "Archive it instead" in response.json()["error"]["message"]
    assert Course.objects.filter(pk=published_course.pk).exists()


def test_a_student_cannot_delete_a_course(
    api_client_no_csrf, student_profile, published_course, enrollment
):
    from apps.courses.models import Course

    response = _client(student_profile.user).delete(f"/api/v1/courses/{published_course.pk}/")
    assert response.status_code in (403, 404)
    assert Course.objects.filter(pk=published_course.pk).exists()
