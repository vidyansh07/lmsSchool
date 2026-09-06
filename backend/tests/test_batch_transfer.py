"""Moving a student between batches, which here is routine rather than a fix.

The client transfers students often — sideways when a cohort is wrong for them,
upwards when they move to a longer or different programme — so the question this
file answers is not "does the transfer work" but "does the institution still
know the truth afterwards".

Three truths have to survive a move:

* **A transfer is not a drop-out.** Cancelling and re-enrolling would make every
  move look like a lost student followed by a new one, and no report could tell
  the difference.
* **Attendance stays where it happened.** A class attended in January belongs to
  January's batch. It must not follow the student, and it must not vanish.
* **The percentage stays honest anyway.** Read from the current row alone, a
  student who transferred in March looks like they joined in March.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.batches.models import BatchKind, BatchStatus
from apps.common.exceptions import ApplicationError
from apps.enrollments.models import (
    ACCESS_GRANTING_STATUSES,
    LIVE_STATUSES,
    SEAT_HOLDING_STATUSES,
    EnrollmentStatus,
)
from apps.enrollments.services import (
    enrol_student,
    set_enrollment_status,
    transfer_attendance_summary,
    transfer_student,
)


@pytest.fixture
def second_batch(admin_user, published_course, trainer_profile_two):
    """Another batch on the same course, with room on it."""
    from apps.batches.services import create_batch, set_batch_status

    today = timezone.localdate()
    created = create_batch(
        actor=admin_user,
        name="Linux Essentials — Evening transfer target",
        course=published_course,
        trainer=trainer_profile_two,
        start_date=today - timedelta(days=3),
        end_date=today + timedelta(days=70),
        capacity=5,
    )
    return set_batch_status(batch=created, target=BatchStatus.ACTIVE, actor=admin_user)


# ---------------------------------------------------------------------------
# A batch has a kind
# ---------------------------------------------------------------------------


def test_a_batch_defaults_to_regular(batch):
    assert batch.kind == BatchKind.REGULAR


@pytest.mark.django_db
def test_a_batch_can_be_an_internship_or_modular(admin_user, batch):
    """Recorded, not inferred from the batch's name, which is what screens did."""
    for kind in (BatchKind.INTERNSHIP, BatchKind.MODULAR, BatchKind.REGULAR):
        batch.kind = kind
        batch.save(update_fields=["kind"])
        batch.refresh_from_db()
        assert batch.kind == kind


# ---------------------------------------------------------------------------
# The move itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_transfer_leaves_two_linked_rows(admin_user, enrollment, second_batch):
    moved = transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Morning cohort clashes with their job",
    )

    enrollment.refresh_from_db()
    assert enrollment.status == EnrollmentStatus.TRANSFERRED
    assert enrollment.transferred_to == moved
    assert moved.transferred_from == enrollment
    assert moved.batch == second_batch
    assert moved.student == enrollment.student


@pytest.mark.django_db
def test_a_transfer_is_not_a_cancellation(admin_user, enrollment, second_batch):
    """The distinction this whole design exists for.

    With one status for both, every transfer is counted as a student lost — and
    the number that reaches whoever is worried about drop-out is wrong in the
    direction that causes meetings.
    """
    transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Moved to the evening cohort",
    )

    enrollment.refresh_from_db()
    assert enrollment.status != EnrollmentStatus.CANCELLED
    assert enrollment.was_moved is True


@pytest.mark.django_db
def test_the_old_row_frees_its_seat_and_grants_no_access(admin_user, enrollment, second_batch):
    transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Wrong cohort",
    )
    enrollment.refresh_from_db()

    assert enrollment.status not in SEAT_HOLDING_STATUSES
    assert enrollment.status not in ACCESS_GRANTING_STATUSES
    assert enrollment.status not in LIVE_STATUSES
    assert enrollment.grants_access() is False


@pytest.mark.django_db
def test_the_student_can_be_moved_back_later(admin_user, enrollment, batch, second_batch):
    """The uniqueness constraint must not treat the row they left as a block.

    Otherwise a student who moves out of a batch can never return to it, and the
    refusal surfaces weeks later as an unexplained conflict.
    """
    moved = transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Trying the evening cohort",
    )

    back = transfer_student(
        enrollment=moved,
        target_batch=batch,
        actor=admin_user,
        reason="Evening did not suit them either",
    )

    assert back.batch == batch
    assert back.pk not in {enrollment.pk, moved.pk}


@pytest.mark.django_db
def test_an_upgrade_is_recorded_rather_than_inferred(admin_user, enrollment, second_batch):
    """Nothing about the two batches says which kind of move this was.

    "Moved to a longer programme" and "moved because the first batch was wrong"
    look identical afterwards, and only the person doing it knows which it was.
    """
    second_batch.kind = BatchKind.INTERNSHIP
    second_batch.save(update_fields=["kind"])

    transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Completed the classroom module, moving to the internship",
        is_upgrade=True,
    )

    enrollment.refresh_from_db()
    assert enrollment.is_upgrade is True


@pytest.mark.django_db
def test_a_lateral_transfer_is_not_marked_as_an_upgrade(admin_user, enrollment, second_batch):
    transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Timing",
    )

    enrollment.refresh_from_db()
    assert enrollment.is_upgrade is False


# ---------------------------------------------------------------------------
# What a transfer may not do
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_transfer_cannot_get_a_student_into_a_full_batch(
    admin_user, enrollment, second_batch, other_student_profile
):
    """A move is not a side door around capacity."""
    from apps.enrollments.services import CapacityError

    second_batch.capacity = 1
    second_batch.save(update_fields=["capacity"])
    enrol_student(student=other_student_profile, batch=second_batch, actor=admin_user)

    with pytest.raises(CapacityError):
        transfer_student(
            enrollment=enrollment,
            target_batch=second_batch,
            actor=admin_user,
            reason="Squeeze them in",
        )

    enrollment.refresh_from_db()
    assert enrollment.status != EnrollmentStatus.TRANSFERRED


@pytest.mark.django_db
def test_moving_to_the_same_batch_is_refused(admin_user, enrollment, batch):
    with pytest.raises(ApplicationError, match="already on that batch"):
        transfer_student(
            enrollment=enrollment, target_batch=batch, actor=admin_user, reason="No-op"
        )


@pytest.mark.django_db
def test_a_reason_is_required(admin_user, enrollment, second_batch):
    """It is the only thing that explains the move afterwards."""
    for reason in ("", "   "):
        with pytest.raises(ApplicationError, match="why"):
            transfer_student(
                enrollment=enrollment,
                target_batch=second_batch,
                actor=admin_user,
                reason=reason,
            )


@pytest.mark.django_db
def test_a_finished_enrolment_is_not_transferred_anywhere(admin_user, enrollment, second_batch):
    set_enrollment_status(
        enrollment=enrollment, target=EnrollmentStatus.COMPLETED, actor=admin_user
    )

    with pytest.raises(ApplicationError, match="cannot be transferred"):
        transfer_student(
            enrollment=enrollment,
            target_batch=second_batch,
            actor=admin_user,
            reason="They finished, but move them anyway",
        )


@pytest.mark.django_db
def test_a_transferred_row_cannot_be_moved_on_directly(admin_user, enrollment, second_batch):
    """The chain advances from the *new* row, never from the one left behind."""
    transfer_student(
        enrollment=enrollment, target_batch=second_batch, actor=admin_user, reason="Moved"
    )
    enrollment.refresh_from_db()

    with pytest.raises(ApplicationError, match="cannot be transferred"):
        transfer_student(
            enrollment=enrollment,
            target_batch=second_batch,
            actor=admin_user,
            reason="Again",
        )


@pytest.mark.django_db
def test_the_status_cannot_be_set_to_transferred_by_hand(admin_user, enrollment):
    """A row saying "transferred" that points nowhere is worse than "cancelled".

    A report would count it as a move and then be unable to say where to.
    """
    with pytest.raises(ApplicationError):
        set_enrollment_status(
            enrollment=enrollment, target=EnrollmentStatus.TRANSFERRED, actor=admin_user
        )


# ---------------------------------------------------------------------------
# The chain, and the honest percentage
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_chain_reads_the_same_from_either_end(admin_user, enrollment, second_batch):
    moved = transfer_student(
        enrollment=enrollment, target_batch=second_batch, actor=admin_user, reason="Moved"
    )
    enrollment.refresh_from_db()

    assert [row.pk for row in enrollment.transfer_chain()] == [enrollment.pk, moved.pk]
    assert [row.pk for row in moved.transfer_chain()] == [enrollment.pk, moved.pk]


@pytest.mark.django_db
def test_a_single_enrolment_is_a_chain_of_one(enrollment):
    assert [row.pk for row in enrollment.transfer_chain()] == [enrollment.pk]


@pytest.mark.django_db
def test_attendance_is_summed_across_the_move(admin_user, enrollment, second_batch, batch):
    """The client's requirement, stated as arithmetic.

    Two classes attended on the old batch and one on the new is 3 of 3 — not the
    1 of 1 that reading the current row alone would report.
    """
    from apps.attendance.models import AttendanceRecord, AttendanceStatus
    from apps.sessions.models import ClassSession, SessionStatus

    def _class(on_batch, day_offset):
        return ClassSession.objects.create(
            batch=on_batch,
            session_date=timezone.localdate() - timedelta(days=day_offset),
            start_time="09:00",
            end_time="11:00",
            status=SessionStatus.COMPLETED,
        )

    for offset in (10, 9):
        AttendanceRecord.objects.create(
            session=_class(batch, offset), enrollment=enrollment, status=AttendanceStatus.PRESENT
        )

    moved = transfer_student(
        enrollment=enrollment, target_batch=second_batch, actor=admin_user, reason="Moved"
    )
    AttendanceRecord.objects.create(
        session=_class(second_batch, 1), enrollment=moved, status=AttendanceStatus.PRESENT
    )

    summary = transfer_attendance_summary(moved)

    assert summary["attended"] == 3
    assert summary["total_sessions"] == 3
    assert summary["percentage"] == 100
    assert summary["spans_batches"] is True
    assert len(summary["per_batch"]) == 2
    assert sum(1 for row in summary["per_batch"] if row["is_current"]) == 1


@pytest.mark.django_db
def test_attendance_with_nothing_recorded_is_none_not_zero(enrollment):
    """A student whose classes have not happened yet has no percentage.

    Reporting 0% would read as a failure, and would put them on a risk list on
    their first day.
    """
    summary = transfer_attendance_summary(enrollment)

    assert summary["percentage"] is None
    assert summary["attended"] == 0
    assert summary["spans_batches"] is False


# ---------------------------------------------------------------------------
# The record of it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_transfer_is_audited_with_both_batches(admin_user, enrollment, second_batch):
    from apps.audit.models import AuditAction, AuditLog

    from_code = enrollment.batch.code
    transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Morning clashes with work",
    )

    entry = AuditLog.objects.filter(
        action=AuditAction.ENROLLMENT_TRANSFERRED, resource_id=str(enrollment.pk)
    ).first()
    assert entry is not None
    assert entry.context["from_batch"] == from_code
    assert entry.context["to_batch"] == second_batch.code
    assert entry.context["reason"] == "Morning clashes with work"
    assert entry.context["is_upgrade"] is False


@pytest.mark.django_db
def test_an_upgrade_is_audited_as_its_own_action(admin_user, enrollment, second_batch):
    """So "how many students upgraded this quarter?" is one query, not a guess."""
    from apps.audit.models import AuditAction, AuditLog

    transfer_student(
        enrollment=enrollment,
        target_batch=second_batch,
        actor=admin_user,
        reason="Moving to the internship",
        is_upgrade=True,
    )

    assert AuditLog.objects.filter(
        action=AuditAction.ENROLLMENT_UPGRADED, resource_id=str(enrollment.pk)
    ).exists()
