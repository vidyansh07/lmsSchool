"""Role and capability registry.

Phase 0 shipped role classes (`IsAdmin`, `IsTrainer`, …). Phase 1 replaces the
*decision* those classes made with a capability lookup, for two reasons:

1. Views should state what they need ("may deactivate a user"), not who is
   allowed. When a fourth role arrives — coordinator, accountant, parent — the
   change is one entry in :data:`ROLE_CAPABILITIES`, not an audit of every view.
2. Role checks scattered through views drift. One table cannot.

The role classes still exist and still work; they are now thin wrappers so the
matrix below is the single source of truth.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    """Coarse platform roles.

    Values are stored in the database, so they are stable strings; labels are
    display-only and may be translated. Add a role here *and* in
    :data:`ROLE_CAPABILITIES` — a role with no entry has no capabilities, which
    fails closed.
    """

    SUPERADMIN = "superadmin", _("Superadmin")
    ADMIN = "admin", _("Administrator")
    MANAGER = "manager", _("Manager")
    TRAINER = "trainer", _("Trainer")
    STUDENT = "student", _("Student")


class Capability(models.TextChoices):
    """Every distinct thing an actor may be permitted to do.

    Naming is `<resource>.<action>`; `*_own` variants act on the caller's own
    record and are additionally constrained by object-level checks.
    """

    # --- User administration
    USER_VIEW_ANY = "user.view_any", _("View any user")
    USER_CREATE = "user.create", _("Create users")
    USER_UPDATE_ANY = "user.update_any", _("Update any user")
    USER_SET_ACTIVE = "user.set_active", _("Activate or deactivate users")
    USER_CHANGE_ROLE = "user.change_role", _("Change a user's role")

    # --- Own account
    PROFILE_VIEW_OWN = "profile.view_own", _("View own profile")
    PROFILE_UPDATE_OWN = "profile.update_own", _("Update own profile")

    # --- Student records
    STUDENT_VIEW_ANY = "student.view_any", _("View any student")
    STUDENT_CREATE = "student.create", _("Create students")
    STUDENT_UPDATE_ANY = "student.update_any", _("Update any student")
    STUDENT_SET_FEE_STATUS = "student.set_fee_status", _("Change a student's fee status")

    # --- Trainer records
    TRAINER_VIEW_ANY = "trainer.view_any", _("View any trainer")
    TRAINER_CREATE = "trainer.create", _("Create trainers")
    TRAINER_UPDATE_ANY = "trainer.update_any", _("Update any trainer")

    # --- Course catalogue
    #
    # These are the *global* course rights. A trainer holds none of them by
    # default: authoring rights are granted per course through
    # ``courses.CourseAssignment``, so a trainer can edit the courses they were
    # assigned and nothing else. Granting a trainer role a global right here is
    # a deliberate, one-line configuration change.
    # --- Platform administration (superadmin only)
    PLATFORM_CONFIGURE = "platform.configure", _("Change platform-wide settings")
    AUDIT_VIEW = "audit.view", _("Read the audit trail")

    # --- Academic configuration
    ACADEMIC_CONFIGURE = "academic.configure", _("Change academic rules")

    CATEGORY_MANAGE = "category.manage", _("Manage course categories")
    COURSE_VIEW_ANY = "course.view_any", _("View any course, including drafts")
    COURSE_CREATE = "course.create", _("Create courses")
    COURSE_UPDATE_ANY = "course.update_any", _("Edit any course")
    COURSE_PUBLISH_ANY = "course.publish_any", _("Change the status of any course")
    COURSE_ASSIGN_AUTHORS = "course.assign_authors", _("Assign authors to a course")

    # --- Batches, schedules and enrolment
    #
    # As with courses, a trainer holds no *global* batch right. What they may
    # see comes from being the assigned trainer on a batch, resolved per record
    # in ``apps.batches.access``.
    BATCH_VIEW_ANY = "batch.view_any", _("View any batch")
    BATCH_CREATE = "batch.create", _("Create batches")
    BATCH_UPDATE_ANY = "batch.update_any", _("Edit any batch")
    BATCH_MANAGE_SCHEDULE = "batch.manage_schedule", _("Manage batch schedules")
    ENROLMENT_VIEW_ANY = "enrolment.view_any", _("View any enrolment")
    ENROLMENT_CREATE = "enrolment.create", _("Enrol students")
    ENROLMENT_UPDATE_ANY = "enrolment.update_any", _("Change any enrolment's status")

    # --- Academic operations
    #
    # `ATTENDANCE_MARK_OWN` is held by nobody globally: a trainer marks the
    # register for the batches they teach, resolved per session in
    # `apps.sessions.access`. `ATTENDANCE_CORRECT_ANY` is the override that
    # lets an administrator fix a mistake on somebody else's class.
    SESSION_MANAGE_ANY = "session.manage_any", _("Manage any class session")
    ATTENDANCE_CORRECT_ANY = "attendance.correct_any", _("Correct attendance on any class")
    ATTENDANCE_VIEW_ANY = "attendance.view_any", _("View any attendance record")


#: Capabilities every authenticated, active user has regardless of role.
BASE_CAPABILITIES: frozenset[str] = frozenset(
    {
        Capability.PROFILE_VIEW_OWN,
        Capability.PROFILE_UPDATE_OWN,
    }
)

#: The authorization matrix. This is the only place a role is turned into
#: permissions. Roles absent from this mapping get `BASE_CAPABILITIES` only.
#:
#: Read it as a ladder: superadmin ⊃ admin ⊃ manager, then two scoped roles that
#: hold almost nothing globally because their reach comes from per-record
#: assignment instead (see `courses.access` and `batches.access`).

#: What a manager may do: run academic operations day to day.
_MANAGER_CAPABILITIES = frozenset(
    {
        Capability.USER_VIEW_ANY,
        Capability.STUDENT_VIEW_ANY,
        Capability.STUDENT_CREATE,
        Capability.STUDENT_UPDATE_ANY,
        Capability.STUDENT_SET_FEE_STATUS,
        Capability.TRAINER_VIEW_ANY,
        Capability.CATEGORY_MANAGE,
        Capability.COURSE_VIEW_ANY,
        Capability.COURSE_CREATE,
        Capability.COURSE_UPDATE_ANY,
        Capability.COURSE_PUBLISH_ANY,
        Capability.COURSE_ASSIGN_AUTHORS,
        Capability.BATCH_VIEW_ANY,
        Capability.BATCH_CREATE,
        Capability.BATCH_UPDATE_ANY,
        Capability.BATCH_MANAGE_SCHEDULE,
        Capability.ENROLMENT_VIEW_ANY,
        Capability.ENROLMENT_CREATE,
        Capability.ENROLMENT_UPDATE_ANY,
        Capability.SESSION_MANAGE_ANY,
        Capability.ATTENDANCE_CORRECT_ANY,
        Capability.ATTENDANCE_VIEW_ANY,
    }
)

#: What an administrator adds on top: authority over people and their accounts.
_ADMIN_ONLY_CAPABILITIES = frozenset(
    {
        Capability.USER_CREATE,
        Capability.USER_UPDATE_ANY,
        Capability.USER_SET_ACTIVE,
        Capability.USER_CHANGE_ROLE,
        Capability.TRAINER_CREATE,
        Capability.TRAINER_UPDATE_ANY,
        Capability.ACADEMIC_CONFIGURE,
        Capability.AUDIT_VIEW,
    }
)

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    # Every capability, including ones added later — a superadmin must never be
    # locked out of a feature because somebody forgot to list it here.
    UserRole.SUPERADMIN: frozenset(Capability.values),
    UserRole.ADMIN: BASE_CAPABILITIES | _MANAGER_CAPABILITIES | _ADMIN_ONLY_CAPABILITIES,
    # A manager runs academic operations but cannot change who somebody *is*:
    # no account creation, no role changes, no platform settings. That keeps
    # "can run the school" and "can grant themselves power" separate.
    UserRole.MANAGER: BASE_CAPABILITIES | _MANAGER_CAPABILITIES,
    # Trainers and students hold no global management capability. What they may
    # touch comes from per-record assignment, which is the whole point of
    # §16's "trainer only assigned batches/content".
    UserRole.TRAINER: BASE_CAPABILITIES,
    UserRole.STUDENT: BASE_CAPABILITIES,
}


def capabilities_for(role: str, *, is_superuser: bool = False) -> frozenset[str]:
    """Resolve the capability set for a role.

    Superusers are platform operators and hold every capability. Role-level
    capability does not bypass object-level ownership checks — a superadmin can
    reach any *record*, but ownership rules still decide whose data is whose
    where that distinction matters.
    """
    if is_superuser:
        return frozenset(Capability.values)
    return ROLE_CAPABILITIES.get(role, BASE_CAPABILITIES)


def has_capability(user, capability: str) -> bool:
    """Authoritative check. Never consults anything the client supplied."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    return capability in capabilities_for(user.role, is_superuser=user.is_superuser)
