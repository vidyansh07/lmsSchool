"""Announcement access.

Two questions, and they have different answers.

**Who may read one?** Whoever it is addressed to. An announcement to everyone is
readable by everyone signed in; one to a batch by the people on that batch and
the staff who can already see that batch; one to named people by those people.

**Who may write one?** §7.3 says admin, manager or an *authorized* trainer. A
trainer's authority is per batch, as everywhere else: they may address the
batches they teach and the courses they author, and nothing wider. Announcing to
everyone needs the global capability.

**Which centre is it?** See the comment above :func:`_one_centres_notices`. This
is the one model in the branch work where the nullable-batch shortcut is wrong,
because for an announcement a null batch does not mean "every batch".
"""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.roles import Capability, has_capability
from apps.batches import access as batch_access
from apps.organisation.scoping import actor_branch_id, is_unbounded

from .models import Announcement, Audience

# The audience, not the null batch, is what makes a notice institution-wide.
#
# `scope_to_branch_or_shared` is the right helper for an assignment or a
# project, where `batch IS NULL` means "set for every batch running the course".
# It is the wrong one here, and the model says why: the
# `announcement_audience_matches_target` constraint requires `batch IS NULL` for
# `selected` and `course` as well as for `everyone`. Reading a null batch as
# "belongs to no centre" therefore classified every notice addressed to *named
# people* as institution-wide and handed it — title, body, and a headcount of
# its recipients — to the capability holder at every other centre, who could
# then edit it and take it down.
#
# So the rule is stated in the terms the model itself uses. `everyone` is the
# one audience that means the institution. Everything else belongs to a centre:
# a batch notice to its batch's centre, a course or a private notice to the
# centre of whoever wrote it. `created_by` is SET_NULL, so a notice whose author
# is gone belongs to no centre and only an unbounded operator reaches it — the
# same fail-closed reading an orphaned export job already gets.


def _one_centres_notices(branch_id) -> Q:
    """The notices that belong to one particular centre."""
    return Q(batch__branch_id=branch_id) | Q(batch__isnull=True, created_by__branch_id=branch_id)


def scope_board_to_branch(queryset: QuerySet[Announcement], user) -> QuerySet[Announcement]:
    """What a capability holder may *read*: their centre's board, plus everyone's."""
    if is_unbounded(user):
        return queryset
    institution_wide = Q(audience=Audience.EVERYONE)
    branch_id = actor_branch_id(user)
    if branch_id is None:
        return queryset.filter(institution_wide)
    return queryset.filter(institution_wide | _one_centres_notices(branch_id)).distinct()


def scope_board_management_to_branch(
    queryset: QuerySet[Announcement], user
) -> QuerySet[Announcement]:
    """What a capability holder may *change*: their own centre's board only.

    Deliberately narrower than the read scope. An institution-wide notice is
    readable everywhere, because that is what addressing everyone means — but it
    is still somebody's notice, and a manager in one city editing or archiving
    the notice another city put up is the same cross-centre write as any other.
    A manager keeps their own centre's `everyone` notices through the second
    clause, because they are the ones who wrote them.
    """
    if is_unbounded(user):
        return queryset
    branch_id = actor_branch_id(user)
    if branch_id is None:
        return queryset.none()
    return queryset.filter(_one_centres_notices(branch_id)).distinct()


def _authored_course_notices(user) -> Q:
    """Notices about a course this trainer is assigned to — at their own centre.

    The course catalogue is institution-wide and a course assignment is not
    branch-aware, so without the second half a trainer assigned to the shared
    Linux course would read, and through `manageable_announcements` edit, every
    centre's notices about its own sitting of it. A trainer with no centre
    reaches none of them, the same fail-closed answer as everywhere else.
    """
    from apps.courses.access import assigned_course_ids

    authored = assigned_course_ids(user)
    branch_id = actor_branch_id(user)
    if not authored or branch_id is None:
        return Q(pk__isnull=True)
    return Q(course_id__in=authored) & _one_centres_notices(branch_id)


def _notices_to_teaching_staff(user) -> Q:
    """Notices addressed to the trainers of this person's centre.

    One written by an unbounded operator belongs to no centre and reaches the
    teaching staff everywhere — the same reading `audience_for` gives it.
    """
    branch_id = actor_branch_id(user)
    if branch_id is None:
        return Q(pk__isnull=True)
    return Q(audience=Audience.TRAINERS) & (
        Q(created_by__branch_id=branch_id) | Q(created_by__branch__isnull=True)
    )


def announcement_branch_id(announcement: Announcement):
    """The centre a notice belongs to, or ``None`` for an institution-wide one.

    The row-level twin of the two querysets above. The publication fan-out uses
    it so that who gets *told* about a notice cannot drift from who can read it
    on the board.
    """
    if announcement.audience == Audience.EVERYONE:
        return None
    if announcement.batch_id:
        return announcement.batch.branch_id
    return announcement.created_by.branch_id if announcement.created_by_id else None


def visible_announcements(user) -> QuerySet[Announcement]:
    """The noticeboard, as this person sees it."""
    base = Announcement.objects.with_related()

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return scope_board_to_branch(base, user)

    scope = Q(audience=Audience.EVERYONE) | Q(audience=Audience.SELECTED, recipients=user)

    trainer = batch_access.trainer_profile(user)
    if trainer is not None:
        # A trainer sees what they may write, plus what is addressed to them.
        scope |= Q(batch__trainer=trainer) | Q(created_by=user)
        scope |= _authored_course_notices(user)
        scope |= _notices_to_teaching_staff(user)
        return base.filter(scope).distinct()

    student = batch_access.student_profile(user)
    if student is not None:
        from apps.enrollments.models import Enrollment

        rows = Enrollment.objects.granting_access().filter(student=student)
        live = [row for row in rows if row.grants_access()]
        if live:
            scope |= Q(batch_id__in=[row.batch_id for row in live]) | Q(
                course_id__in=[row.course_id for row in live]
            )
        # A student sees the noticeboard, never a draft.
        return base.live().filter(scope).distinct()

    return base.filter(scope).distinct()


def manageable_announcements(user) -> QuerySet[Announcement]:
    base = Announcement.objects.with_related()

    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return scope_board_management_to_branch(base, user)
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return base.none()

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return base.none()

    scope = Q(batch__trainer=trainer) | Q(created_by=user)
    scope |= _authored_course_notices(user)
    return base.filter(scope).distinct()


def can_publish_to(user, *, audience: str, course=None, batch=None) -> bool:
    """May this person address this audience?"""
    if has_capability(user, Capability.ANNOUNCEMENT_MANAGE_ANY):
        return True

    trainer = batch_access.trainer_profile(user)
    if trainer is None:
        return False

    if audience == Audience.BATCH and batch is not None:
        return batch.trainer_id == trainer.pk
    if audience == Audience.COURSE and course is not None:
        from apps.courses.access import can_manage_course

        return can_manage_course(user, course) or course.batches.filter(trainer=trainer).exists()
    # Everyone, and naming arbitrary people, stay with the capability holders.
    return False


def can_manage(user, announcement: Announcement) -> bool:
    """Implemented through the queryset alone, so the two cannot disagree.

    The capability short-circuit that used to sit above this line was harmless
    while `manageable_announcements` returned everything to a capability
    holder. Once that queryset narrowed to a centre, the short-circuit answered
    `True` for a notice from another one — the two halves of the same rule
    giving different answers, which is the drift CONVENTIONS §3.5 exists to
    prevent.
    """
    return manageable_announcements(user).filter(pk=announcement.pk).exists()
