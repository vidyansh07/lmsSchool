"""Who may see and make an admission.

An admission is a fact about a student, so it borrows that question's answer
rather than inventing a second one: you may read an admission exactly when
you may read the student it belongs to (`students.access.visible_students`),
and the capability to make one is the capability to enrol
(`enrolment.create`). Two rules where one would do is how two screens end up
disagreeing about who may see what.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.students import access as students_access

from .models import Admission


def visible_admissions(user) -> QuerySet[Admission]:
    base = Admission.objects.with_related()
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    return base.filter(student__in=students_access.visible_students(user))


def can_manage_admissions(user) -> bool:
    """Make one, change one, cancel one."""
    return has_capability(user, Capability.ENROLMENT_CREATE)
