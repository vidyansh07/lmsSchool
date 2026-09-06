"""Deletion is reversible, and invisible until it is undone.

Two promises are being checked, and they pull in opposite directions:

* A deleted record must not appear in **any** normal query — not a list
  endpoint, not a reverse relation, not a report. The failure mode is one screen
  out of forty still showing it, which is why the default manager filters rather
  than each call site remembering to.
* A deleted record must still be **reachable** where history needs it. A child
  pointing at a deleted parent has to be able to name that parent, or the audit
  trail becomes unreadable at exactly the moment somebody is trying to work out
  what happened.

The second is easy to break while satisfying the first, and it breaks silently,
so it is checked as carefully as the first.
"""

from __future__ import annotations

import pytest
from django.apps import apps as django_apps

from apps.accounts.roles import Capability, UserRole, has_capability
from apps.common.deletion import purge, restore, soft_delete
from apps.common.exceptions import ApplicationError, ConflictError
from apps.common.models import SoftDeleteModel


def _where_clause(queryset) -> str:
    """Just the WHERE of a queryset's SQL.

    The whole statement is useless for this: every soft-deletable model selects
    a ``deleted_at`` column, so searching the full SQL for the word finds it
    whether or not anything is being filtered. The first version of this test
    did exactly that and passed on a manager that filtered nothing.
    """
    sql = str(queryset.query)
    _, separator, where = sql.partition(" WHERE ")
    return where if separator else ""


def soft_deletable_models() -> list[type]:
    """Every concrete model that opted into reversible deletion."""
    return [
        model
        for model in django_apps.get_models()
        if issubclass(model, SoftDeleteModel) and not model._meta.abstract
    ]


# ---------------------------------------------------------------------------
# The contract every adopting model must satisfy
# ---------------------------------------------------------------------------


def test_there_is_something_to_check():
    """A refactor that emptied this list would make the whole file vacuous."""
    assert len(soft_deletable_models()) >= 3


@pytest.mark.parametrize(
    "model", soft_deletable_models(), ids=[m._meta.label for m in soft_deletable_models()]
)
def test_the_default_manager_hides_deleted_rows(model):
    """Checked by looking at the SQL, not at the manager's name.

    Most models here define a domain queryset and assign it as ``objects``,
    which silently *overrides* the filtering manager inherited from
    `SoftDeleteModel`. A model in that state has all three columns, a clean
    migration, and returns deleted rows from every query — and nothing about it
    looks wrong. `soft_delete_managers` is the fix; this is what notices when
    somebody adopts the base class without it.
    """
    assert model._default_manager.name == "objects"
    assert "deleted_at" in _where_clause(model._default_manager.all()), (
        f"{model._meta.label}.objects does not filter deleted rows — it probably "
        f"assigns its own queryset directly instead of using soft_delete_managers()"
    )


@pytest.mark.parametrize(
    "model", soft_deletable_models(), ids=[m._meta.label for m in soft_deletable_models()]
)
def test_every_model_offers_a_way_to_see_deleted_rows(model):
    """The recovery screens need one, and it must be the same name everywhere."""
    assert hasattr(model, "all_objects")
    assert "deleted_at" not in _where_clause(model.all_objects.all())


@pytest.mark.parametrize(
    "model", soft_deletable_models(), ids=[m._meta.label for m in soft_deletable_models()]
)
def test_the_base_manager_does_not(model):
    """The footgun this test exists for.

    Django follows a forward foreign key through the *base* manager. A model
    that defines `class Meta:` without inheriting `SoftDeleteModel.Meta` loses
    `base_manager_name`, Django falls back to the filtering manager, and reading
    `enrollment.batch` for a deleted batch starts raising `DoesNotExist` — in
    the audit trail, in a report, anywhere history is read.

    Nothing about that failure points at the missing Meta inheritance, and it
    would be found in production by somebody trying to answer a question about a
    record that had been removed. So it is found here instead.
    """
    assert model._meta.base_manager_name == "all_objects", (
        f"{model._meta.label} does not inherit SoftDeleteModel.Meta, so following a "
        f"foreign key to a deleted {model.__name__} will raise instead of resolving"
    )


@pytest.mark.parametrize(
    "model", soft_deletable_models(), ids=[m._meta.label for m in soft_deletable_models()]
)
def test_partial_uniqueness_ignores_deleted_rows(model):
    """A deleted row must not go on reserving the slot it used to hold.

    Otherwise a soft delete cannot be undone by doing the thing again — remove a
    student from a batch, try to enrol them back, and the constraint refuses
    because the deleted row is still there. That is not soft deletion; it is a
    ban with extra steps.

    Field-level `unique=True` is exempt and deliberately so: the columns using it
    here are system-allocated codes from a monotonic sequence, which are never
    reissued, so a deleted row holding its own code forever is correct.
    """
    for constraint in model._meta.constraints:
        fields = getattr(constraint, "fields", None)
        if not fields:  # a check constraint, or an expression index
            continue
        condition = getattr(constraint, "condition", None)
        assert condition is not None and "deleted_at" in str(condition), (
            f"{model._meta.label}.{constraint.name} is unique across deleted rows too, "
            f"so a deleted record permanently blocks recreating it"
        )


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_deleted_record_leaves_every_normal_query(admin_user, batch):
    from apps.batches.models import Batch

    soft_delete(instance=batch, actor=admin_user, reason="Created by mistake")

    assert not Batch.objects.filter(pk=batch.pk).exists()
    assert Batch.all_objects.filter(pk=batch.pk).exists()
    assert Batch.all_objects.dead().filter(pk=batch.pk).exists()


@pytest.mark.django_db
def test_a_deleted_record_leaves_reverse_relations_too(admin_user, batch, enrollment):
    """The half that a per-call-site filter would miss.

    `course.batches` is a reverse relation, and nobody writing a course screen
    thinks of it as a query they have to filter.
    """
    course = batch.course
    assert batch in course.batches.all()

    soft_delete(instance=batch, actor=admin_user, reason="Merged into another cohort")

    assert batch not in course.batches.all()


@pytest.mark.django_db
def test_a_child_can_still_name_its_deleted_parent(admin_user, batch, enrollment):
    """Reading history must not start throwing once a record is removed."""
    from apps.enrollments.models import Enrollment

    soft_delete(instance=batch, actor=admin_user, reason="Cancelled")

    row = Enrollment.all_objects.get(pk=enrollment.pk)
    assert row.batch.pk == batch.pk
    assert row.batch.is_deleted is True


@pytest.mark.django_db
def test_deletion_records_who_and_why(admin_user, batch):
    soft_delete(instance=batch, actor=admin_user, reason="Duplicate of GRS-B-00007")

    batch.refresh_from_db()
    assert batch.is_deleted
    assert batch.deleted_by == admin_user
    assert batch.delete_reason == "Duplicate of GRS-B-00007"


@pytest.mark.django_db
def test_deletion_is_audited(admin_user, batch):
    from apps.audit.models import AuditAction, AuditLog

    soft_delete(instance=batch, actor=admin_user, reason="Cancelled by the client")

    entry = AuditLog.objects.filter(
        action=AuditAction.RECORD_DELETED, resource_id=str(batch.pk)
    ).first()
    assert entry is not None
    assert entry.actor == admin_user
    assert entry.context["reason"] == "Cancelled by the client"
    assert entry.context["describes"] == batch.code


@pytest.mark.django_db
def test_deleting_twice_is_not_an_error(admin_user, batch):
    """Two clicks on a delete button is a normal thing for a person to do."""
    soft_delete(instance=batch, actor=admin_user, reason="First")
    first_stamp = batch.deleted_at

    soft_delete(instance=batch, actor=admin_user, reason="Second")

    batch.refresh_from_db()
    assert batch.deleted_at == first_stamp
    assert batch.delete_reason == "First"


# ---------------------------------------------------------------------------
# Cascading, and the part of it that is easy to get wrong
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_children_go_down_with_the_parent(admin_user, batch, enrollment):
    from apps.enrollments.models import Enrollment

    soft_delete(
        instance=batch,
        actor=admin_user,
        reason="Cohort never ran",
        cascade=(Enrollment.all_objects.filter(batch=batch),),
    )

    assert not Enrollment.objects.filter(pk=enrollment.pk).exists()
    assert Enrollment.all_objects.get(pk=enrollment.pk).deleted_at == batch.deleted_at


@pytest.mark.django_db
def test_restore_brings_back_only_what_this_deletion_took(
    admin_user, batch, enrollment, other_enrollment
):
    """The subtle one.

    A student who left the batch last week is not a student who was on it when
    the batch was cancelled. Restoring the batch must not quietly re-enrol them:
    that would be inventing a decision nobody made, and on a fee-bearing record.
    """
    from apps.enrollments.models import Enrollment

    soft_delete(instance=other_enrollment, actor=admin_user, reason="Withdrew")
    withdrawn_stamp = Enrollment.all_objects.get(pk=other_enrollment.pk).deleted_at

    soft_delete(
        instance=batch,
        actor=admin_user,
        reason="Cohort cancelled",
        cascade=(Enrollment.all_objects.filter(batch=batch),),
    )
    restore(
        instance=batch,
        actor=admin_user,
        cascade=(Enrollment.all_objects.filter(batch=batch),),
    )

    assert Enrollment.objects.filter(pk=enrollment.pk).exists()
    # Still gone, and still gone for its own reason.
    assert not Enrollment.objects.filter(pk=other_enrollment.pk).exists()
    row = Enrollment.all_objects.get(pk=other_enrollment.pk)
    assert row.deleted_at == withdrawn_stamp
    assert row.delete_reason == "Withdrew"


# ---------------------------------------------------------------------------
# Restoring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_restore_clears_every_deletion_field(admin_user, batch):
    from apps.batches.models import Batch

    soft_delete(instance=batch, actor=admin_user, reason="Wrong course")
    restore(instance=batch, actor=admin_user)

    batch.refresh_from_db()
    assert batch.deleted_at is None
    assert batch.deleted_by is None
    assert batch.delete_reason == ""
    assert Batch.objects.filter(pk=batch.pk).exists()


@pytest.mark.django_db
def test_restoring_a_live_record_is_refused(admin_user, batch):
    with pytest.raises(ConflictError):
        restore(instance=batch, actor=admin_user)


@pytest.mark.django_db
def test_restore_is_audited(admin_user, batch):
    from apps.audit.models import AuditAction, AuditLog

    soft_delete(instance=batch, actor=admin_user, reason="Mistake")
    restore(instance=batch, actor=admin_user)

    assert AuditLog.objects.filter(
        action=AuditAction.RECORD_RESTORED, resource_id=str(batch.pk)
    ).exists()


@pytest.mark.django_db
def test_a_removed_student_can_be_enrolled_on_that_batch_again(admin_user, student_profile, batch):
    """The constraint change, stated as the thing it lets a person do.

    Without `deleted_at` in the uniqueness condition, removing an enrolment
    would permanently bar that student from that batch — and the error would
    surface as an unexplained conflict months later.
    """
    from apps.enrollments.services import enrol_student

    first = enrol_student(student=student_profile, batch=batch, actor=admin_user)
    soft_delete(instance=first, actor=admin_user, reason="Enrolled on the wrong cohort")

    second = enrol_student(student=student_profile, batch=batch, actor=admin_user)

    assert second.pk != first.pk


# ---------------------------------------------------------------------------
# Purging — the one act that cannot be undone
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_purge_requires_the_record_to_be_deleted_first(admin_user, batch):
    """Destruction is a second decision, not a stronger first one."""
    with pytest.raises(ApplicationError, match="deleted record"):
        purge(instance=batch, actor=admin_user, reason="Test data")


@pytest.mark.django_db
def test_purge_destroys_the_row_and_leaves_the_audit_entry(admin_user, batch):
    from apps.audit.models import AuditAction, AuditLog
    from apps.batches.models import Batch

    batch_pk = batch.pk
    batch_code = batch.code
    soft_delete(instance=batch, actor=admin_user, reason="Created during a demo")
    purge(instance=batch, actor=admin_user, reason="Retention policy")

    assert not Batch.all_objects.filter(pk=batch_pk).exists()

    entry = AuditLog.objects.filter(
        action=AuditAction.RECORD_PURGED, resource_id=str(batch_pk)
    ).first()
    assert entry is not None
    # Written before the row went, because afterwards there is nothing to
    # describe — and "what was destroyed?" is the whole question.
    assert entry.context["describes"] == batch_code


# ---------------------------------------------------------------------------
# Who may do any of it
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_only_a_superadmin_may_destroy(db):
    """Everything else on the ladder is reversible. This is the exception."""
    from apps.accounts.models import User

    holders = []
    for role in UserRole.values:
        person = User.objects.create_user(
            email=f"purge-{role}@deletion.grras.invalid",
            password="Str0ng-Passphrase!42",
            first_name="Purge",
            last_name=role.title(),
            role=role,
        )
        if has_capability(person, Capability.RECORD_PURGE):
            holders.append(role)

    assert holders == [UserRole.SUPERADMIN]


@pytest.mark.django_db
def test_an_administrator_may_see_and_restore(admin_user, manager_user, counsellor_user):
    assert has_capability(admin_user, Capability.RECORD_VIEW_DELETED)
    assert has_capability(admin_user, Capability.RECORD_RESTORE)
    assert not has_capability(admin_user, Capability.RECORD_PURGE)

    for person in (manager_user, counsellor_user):
        assert not has_capability(person, Capability.RECORD_VIEW_DELETED)
        assert not has_capability(person, Capability.RECORD_RESTORE)
