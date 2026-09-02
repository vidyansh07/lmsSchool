"""Course access control.

Every "may this person see or change this course?" question is answered here.
Views ask; they never decide. That matters because the same question is asked
from six places — catalogue listing, course detail, lesson content, resource
download, video playback, editing — and six copies of the rule would drift.

Three distinct questions, deliberately separate:

``can_view_course``
    May the caller know this course exists, and read its marketing detail?

``can_view_content``
    May the caller read a lesson's body, download its resources, play its video?
    This is a *stricter* question than viewing the course page, and it is where
    enrolment will attach.

``can_manage_course`` / ``can_publish_course``
    May the caller change it?

Enrolment
---------
Phase 3 connected this to real enrolment records. ``is_enrolled`` now asks the
enrolment table, and ``COURSE_CONTENT_REQUIRES_ENROLMENT`` defaults to on — so
a student reaches non-preview content only through a live enrolment.

The seam that made this a two-line change is worth keeping: every content check
routes through ``is_enrolled``, so the rule lives in one place. Suspending an
enrolment or cancelling a batch closes access on the very next request, with no
cache to invalidate and no second copy of the rule to update.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability

from .models import Course, CourseAssignment, CourseAuthorRole, CourseVisibility, PublishStatus

# ---------------------------------------------------------------------------
# Assignment lookup
# ---------------------------------------------------------------------------


def assignment_for(user, course: Course) -> CourseAssignment | None:
    """The caller's authoring row for this course, if any."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    return CourseAssignment.objects.filter(course=course, user=user).first()


def assigned_course_ids(user) -> list[str]:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return []
    return list(CourseAssignment.objects.filter(user=user).values_list("course_id", flat=True))


# ---------------------------------------------------------------------------
# Enrolment
# ---------------------------------------------------------------------------


def _student_profile(user):
    """The caller's student profile, or None if they are not an active student."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    return getattr(user, "student_profile", None)


def is_enrolled(user, course: Course) -> bool:
    """Whether the caller holds an enrolment that opens this course.

    The single definition of "enrolled enough to read the content". Three
    things must hold, and :meth:`Enrollment.grants_access` owns all three: the
    status allows it, the batch has not been cancelled, and today falls inside
    any access window.

    Checked per request rather than cached — suspending an enrolment has to take
    effect immediately, and a cache is a second place for the answer to be
    wrong.
    """
    student = _student_profile(user)
    if student is None:
        return False

    from apps.enrollments.models import Enrollment

    candidates = (
        Enrollment.objects.granting_access()
        .filter(student=student, course=course)
        .select_related("batch")
    )
    return any(enrollment.grants_access() for enrollment in candidates)


def enrolled_course_ids(user) -> list:
    """Courses the caller may open through an enrolment.

    Evaluated in Python rather than as a subquery because ``grants_access``
    also weighs the date window and the batch status — logic that belongs in
    one place, not duplicated into SQL.
    """
    student = _student_profile(user)
    if student is None:
        return []

    from apps.enrollments.models import Enrollment

    enrollments = (
        Enrollment.objects.granting_access().filter(student=student).select_related("batch")
    )
    return [row.course_id for row in enrollments if row.grants_access()]


def content_requires_enrolment() -> bool:
    return bool(getattr(settings, "COURSE_CONTENT_REQUIRES_ENROLMENT", False))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def can_manage_course(user, course: Course) -> bool:
    """Edit the course and its content."""
    if has_capability(user, Capability.COURSE_UPDATE_ANY):
        return True
    assignment = assignment_for(user, course)
    return assignment is not None


def can_publish_course(user, course: Course) -> bool:
    """Change the course's status.

    Stricter than editing: an assigned *editor* may write content but not
    publish it, which is what makes the review step meaningful.
    """
    if has_capability(user, Capability.COURSE_PUBLISH_ANY):
        return True
    assignment = assignment_for(user, course)
    return assignment is not None and assignment.role == CourseAuthorRole.OWNER


def can_view_course(user, course: Course) -> bool:
    """May the caller see that this course exists?"""
    if has_capability(user, Capability.COURSE_VIEW_ANY):
        return True
    if can_manage_course(user, course):
        return True

    # Everyone else sees published courses only. An unpublished course is
    # invisible, not merely uneditable.
    if course.status != PublishStatus.PUBLISHED:
        return False
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    # PRIVATE courses are reachable only by their assigned authors, handled
    # above; a signed-in student cannot see them.
    return course.visibility in (CourseVisibility.PUBLIC, CourseVisibility.INTERNAL)


def can_view_content(user, course: Course, *, lesson=None) -> bool:
    """May the caller read lesson bodies, resources and video for this course?

    Callers must already have passed :func:`can_view_course`; this adds the
    content-level rule on top.
    """
    if not can_view_course(user, course):
        return False
    if can_manage_course(user, course) or has_capability(user, Capability.COURSE_VIEW_ANY):
        return True

    # A free-preview lesson is readable by anyone who can see the course. That
    # is its entire purpose: the sample a prospective student is shown.
    if lesson is not None and getattr(lesson, "is_preview", False):
        return True

    if not content_requires_enrolment():
        return True
    return is_enrolled(user, course)


def visible_courses(user) -> QuerySet[Course]:
    """Every course the caller may see, as a queryset.

    Returning a queryset rather than filtering in Python is what keeps listing
    bounded: the database applies the rule, so a caller cannot page past their
    own visibility.
    """
    base = Course.objects.with_related()

    if has_capability(user, Capability.COURSE_VIEW_ANY):
        return base

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    # Published and discoverable, or assigned to me — never anything else.
    return base.filter(
        Q(
            status=PublishStatus.PUBLISHED,
            visibility__in=(CourseVisibility.PUBLIC, CourseVisibility.INTERNAL),
        )
        | Q(assignments__user=user)
    ).distinct()


def manageable_courses(user) -> QuerySet[Course]:
    """Courses the caller may edit."""
    base = Course.objects.with_related()
    if has_capability(user, Capability.COURSE_UPDATE_ANY):
        return base
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()
    return base.filter(assignments__user=user).distinct()


# ---------------------------------------------------------------------------
# Content-tree visibility
# ---------------------------------------------------------------------------


def visible_modules(user, course: Course):
    """Modules of a course, filtered to what the caller may see."""
    modules = course.modules.all()
    if can_manage_course(user, course) or has_capability(user, Capability.COURSE_VIEW_ANY):
        return modules
    return modules.filter(status=PublishStatus.PUBLISHED, is_visible=True)


def visible_lessons(user, module):
    """Lessons of a module, filtered to what the caller may see.

    A student sees published lessons only — a draft lesson inside a published
    module must not leak, which is exactly the kind of gap that appears when
    filtering happens one level up and not the next.
    """
    lessons = module.lessons.all()
    course = module.course
    if can_manage_course(user, course) or has_capability(user, Capability.COURSE_VIEW_ANY):
        return lessons
    return lessons.filter(status=PublishStatus.PUBLISHED)
