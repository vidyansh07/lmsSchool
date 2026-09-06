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
    # Admissions, not academics. A counsellor brings a student in — registers
    # them, picks the course, opens or chooses the batch, puts a trainer on it —
    # and then hands over. They hold a strict subset of what a manager holds, so
    # the ladder stays a ladder (see `can_administer`).
    COUNSELLOR = "counsellor", _("Counsellor")
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

    # --- Daily status reports
    #
    # A trainer holds none of these, for the same reason they hold no attendance
    # capability: they write the report for the classes they actually took, and
    # that authority is resolved per record in ``apps.dsr.access``. What needs a
    # capability is reaching somebody else's report, correcting one, and ruling
    # on one.
    #
    # Reviewing is separated from managing because they are different acts by
    # different people. A manager approving a report is making a judgement about
    # work somebody else did; correcting the text of one is editing that work.
    DSR_VIEW_ANY = "dsr.view_any", _("View any daily status report")
    DSR_MANAGE_ANY = "dsr.manage_any", _("Create or correct any daily status report")
    DSR_REVIEW = "dsr.review", _("Approve, reject or return a daily status report")

    # --- Performance and reviews
    #
    # Reading a performance picture is separated from writing one down. A
    # manager does both; a role that should see how a batch is doing without
    # being able to put a rating on somebody's record can hold only the first.
    PERFORMANCE_VIEW_ANY = (
        "performance.view_any",
        _("View any student's or trainer's performance"),
    )
    REVIEW_MANAGE_ANY = "review.manage_any", _("Record feedback and performance reviews")

    # --- Assignments
    #
    # A trainer holds none of these globally. Their authority over an assignment
    # comes from teaching its batch or authoring its course, resolved per record
    # in ``apps.assignments.access`` — so an assignment id from somebody else's
    # course buys nothing.
    ASSIGNMENT_VIEW_ANY = "assignment.view_any", _("View any assignment")
    ASSIGNMENT_MANAGE_ANY = "assignment.manage_any", _("Create or edit any assignment")
    ASSIGNMENT_GRADE_ANY = "assignment.grade_any", _("Grade any submission")

    # --- Assessments and results
    ASSESSMENT_VIEW_ANY = "assessment.view_any", _("View any assessment")
    ASSESSMENT_MANAGE_ANY = "assessment.manage_any", _("Create or edit any assessment")
    RESULT_MANAGE_ANY = "result.manage_any", _("Record or import any result")

    # --- Projects
    PROJECT_VIEW_ANY = "project.view_any", _("View any project")
    PROJECT_MANAGE_ANY = "project.manage_any", _("Create or edit any project")
    PROJECT_REVIEW_ANY = "project.review_any", _("Review and grade any project")

    # --- Question bank and examinations
    QUESTION_VIEW_ANY = "question.view_any", _("View the question bank")
    QUESTION_MANAGE_ANY = "question.manage_any", _("Create or edit questions")
    EXAM_VIEW_ANY = "exam.view_any", _("View any examination")
    EXAM_MANAGE_ANY = "exam.manage_any", _("Create or edit any examination")
    EXAM_GRADE_ANY = "exam.grade_any", _("Grade any examination attempt")

    # --- Completion and certificates
    #
    # Approving a completion and issuing a certificate are institutional acts,
    # not teaching ones: a certificate leaves the building and carries the
    # institution's name. Both sit above the manager rung by default.
    COMPLETION_VIEW_ANY = "completion.view_any", _("View any student's completion status")
    COMPLETION_APPROVE = "completion.approve", _("Approve or reject a course completion")
    CERTIFICATE_MANAGE = "certificate.manage", _("Issue, reissue and revoke certificates")

    # --- Communication
    #
    # A trainer holds neither: their announcements reach the batches they teach,
    # resolved per record in `apps.announcements.access`. Addressing everybody is
    # a different act and needs the capability.
    ANNOUNCEMENT_MANAGE_ANY = "announcement.manage_any", _("Announce to any audience")
    DISCUSSION_MODERATE_ANY = "discussion.moderate_any", _("Moderate any discussion")

    # --- Reporting and data tools
    #
    # A trainer holds neither. They can read reports about the batches they
    # teach — resolved per record — and cannot export or bulk-import anything,
    # because both operate across the institution.
    REPORT_VIEW_ANY = "report.view_any", _("Read reports across the institution")
    DATA_EXPORT = "data.export", _("Export data")
    DATA_IMPORT = "data.import", _("Bulk import data")
    # `DATA_EXPORT` above is the right to export at all. This is the separate
    # right to see and cancel somebody *else's* export job. Your own jobs are
    # yours by ownership and need no capability — an export job names what was
    # extracted and by whom, so a list of everybody's is an administrative view.
    EXPORT_VIEW_ANY = "export.view_any", _("View any export job")


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
#: Read it as a ladder: superadmin ⊃ admin ⊃ manager ⊃ counsellor, then two
#: scoped roles that hold almost nothing globally because their reach comes from
#: per-record assignment instead (see `courses.access` and `batches.access`).
#:
#: The containment is not decoration. `can_administer` decides who may touch
#: whose account by comparing capability sets, so two roles holding
#: incomparable sets would be a flat spot in the hierarchy — neither able to
#: administer the other, for no reason a person could explain. Keeping each rung
#: strictly inside the one above is what makes the rule statable in a sentence.

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
        Capability.DSR_VIEW_ANY,
        Capability.DSR_MANAGE_ANY,
        Capability.DSR_REVIEW,
        Capability.PERFORMANCE_VIEW_ANY,
        Capability.REVIEW_MANAGE_ANY,
        Capability.ASSIGNMENT_VIEW_ANY,
        Capability.ASSIGNMENT_MANAGE_ANY,
        Capability.ASSIGNMENT_GRADE_ANY,
        Capability.ASSESSMENT_VIEW_ANY,
        Capability.ASSESSMENT_MANAGE_ANY,
        Capability.RESULT_MANAGE_ANY,
        Capability.PROJECT_VIEW_ANY,
        Capability.PROJECT_MANAGE_ANY,
        Capability.PROJECT_REVIEW_ANY,
        Capability.QUESTION_VIEW_ANY,
        Capability.QUESTION_MANAGE_ANY,
        Capability.EXAM_VIEW_ANY,
        Capability.EXAM_MANAGE_ANY,
        Capability.EXAM_GRADE_ANY,
        Capability.COMPLETION_VIEW_ANY,
        Capability.ANNOUNCEMENT_MANAGE_ANY,
        Capability.DISCUSSION_MODERATE_ANY,
        Capability.REPORT_VIEW_ANY,
        Capability.DATA_EXPORT,
        Capability.DATA_IMPORT,
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
        Capability.COMPLETION_APPROVE,
        Capability.CERTIFICATE_MANAGE,
        Capability.EXPORT_VIEW_ANY,
    }
)

#: What a counsellor may do: bring students in, and stop there.
#:
#: The workflow this serves is one line — register a student, choose the course,
#: open or pick the batch, put a trainer on it, enrol them — and every
#: capability here exists to serve one step of it. Bulk import and export are
#: included because admissions arrive as spreadsheets.
#:
#: Note what is absent, and why:
#:
#: * **Nothing academic.** No attendance, assessment, assignment, project, exam,
#:   DSR or completion right. A counsellor sets the training up; they do not run
#:   it or mark it.
#: * **No `REPORT_VIEW_ANY`.** The report catalogue aggregates the whole
#:   institution and is a management tool. `DATA_EXPORT` is still held, because
#:   exporting the student and batch lists they already work with is part of the
#:   job — and those lists come back through the same scoped querysets, so the
#:   capability cannot widen what they see.
#: * **Nothing about accounts.** No `USER_*` capability, so a counsellor cannot
#:   edit, deactivate or re-role anybody, including the students they created.
#:
#: Every member of this set is also in `_MANAGER_CAPABILITIES`, which is what
#: keeps the ladder a ladder rather than two roles standing side by side. The
#: ladder test asserts it, so the property cannot be lost by accident.
_COUNSELLOR_CAPABILITIES = frozenset(
    {
        # The student record itself, from registration onwards.
        Capability.STUDENT_VIEW_ANY,
        Capability.STUDENT_CREATE,
        Capability.STUDENT_UPDATE_ANY,
        Capability.STUDENT_SET_FEE_STATUS,
        # Reading the catalogue, to choose what somebody is enrolling on.
        Capability.COURSE_VIEW_ANY,
        # Reading trainers, to put one on a batch. Not creating or editing them.
        Capability.TRAINER_VIEW_ANY,
        # Batches: create, choose, timetable, and assign the trainer. Assigning
        # a trainer goes through `batch.update_any` in `batches.access`.
        Capability.BATCH_VIEW_ANY,
        Capability.BATCH_CREATE,
        Capability.BATCH_UPDATE_ANY,
        Capability.BATCH_MANAGE_SCHEDULE,
        # Enrolment, including transfers and status changes.
        Capability.ENROLMENT_VIEW_ANY,
        Capability.ENROLMENT_CREATE,
        Capability.ENROLMENT_UPDATE_ANY,
        # Admissions arrive as spreadsheets and leave as spreadsheets.
        Capability.DATA_IMPORT,
        Capability.DATA_EXPORT,
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
    # A counsellor sets training up and does not run it. Strictly inside the
    # manager rung.
    UserRole.COUNSELLOR: BASE_CAPABILITIES | _COUNSELLOR_CAPABILITIES,
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


def can_grant_role(actor, role: str) -> bool:
    """Whether ``actor`` may hand somebody else this role.

    The rule is containment: you may grant a role only when everything it can do
    is something *you* can already do. Nothing else needs configuring, and the
    ladder cannot be climbed sideways.

    Without this, adding SUPERADMIN in Phase 4 would have opened a privilege
    escalation: an administrator holds ``user.change_role``, so they could set
    somebody's role — including their own account's — to ``superadmin`` and
    thereby acquire ``platform.configure``, a capability the ladder deliberately
    withholds from them.
    """
    if actor is None or not getattr(actor, "is_authenticated", False) or not actor.is_active:
        return False
    granted = ROLE_CAPABILITIES.get(role)
    if granted is None:
        return False
    held = capabilities_for(actor.role, is_superuser=actor.is_superuser)
    return granted <= held


def can_administer(actor, target) -> bool:
    """Whether ``actor`` may administer ``target``'s account.

    ``can_grant_role`` above answers "which role may I hand out?". This answers
    the question nobody had asked: "whose account may I touch at all?" Without
    it the two are not the same rule, and the gap was real — an administrator
    could not promote anyone above themselves, but *could* edit a superadmin's
    email address and then send that address a password-reset link, or simply
    deactivate them. Authority flowed upward through a door nobody had thought
    to close.

    The rule, in order:

    1. **Not yourself.** Administering your own account through the staff
       endpoints would let somebody deactivate themselves, or hand themselves a
       role. Editing your own name and phone number is self-service and lives on
       a different endpoint with a different serializer, which does not accept a
       role at all.
    2. **A superadmin may administer anyone, including another superadmin.**
       That is deliberate and it is the one lateral move allowed: if a superadmin
       account is compromised, somebody has to be able to deactivate it, and an
       institution with one unremovable account is worse off than one where the
       top of the ladder can police itself. Every such act is audited.
    3. **Everybody else may administer strictly less than themselves.** The
       target's role must hold a proper subset of the actor's capabilities. So an
       administrator may administer a manager, a counsellor, a trainer or a
       student, and may not touch another administrator or a superadmin. A
       manager may administer counsellors, trainers and students. Peers cannot
       edit each other, which is what stops two colleagues quietly trading
       privileges.

    This is the second of two gates, not the only one. Every endpoint that
    administers an account also demands a `user.*` capability, and the roles
    below administrator hold none of them — so a manager or counsellor
    satisfying this rule still cannot reach the endpoint. The rule answers
    "whose account, if any?"; the capability answers "may you administer
    accounts at all?".
    """
    if actor is None or not getattr(actor, "is_authenticated", False) or not actor.is_active:
        return False
    if target is None:
        return False
    if getattr(target, "pk", None) is not None and target.pk == actor.pk:
        return False

    held = capabilities_for(actor.role, is_superuser=actor.is_superuser)
    if actor.is_superuser or actor.role == UserRole.SUPERADMIN:
        return True

    theirs = capabilities_for(target.role, is_superuser=target.is_superuser)
    return theirs < held


def has_capability(user, capability: str) -> bool:
    """Authoritative check. Never consults anything the client supplied."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not user.is_active:
        return False
    return capability in capabilities_for(user.role, is_superuser=user.is_superuser)
