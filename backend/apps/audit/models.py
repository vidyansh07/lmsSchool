"""Audit log.

Answers "who did what to which record, when, from where, and did it succeed?"
for every module that will be built on this foundation.

Design constraints
------------------
* **Append-only.** ``save`` refuses updates and ``delete`` is blocked at the
  model level. An audit trail that can be edited is not evidence. Retention
  trimming is a deliberate, separate operation.
* **Survives actor deletion.** ``actor`` is nullable with ``SET_NULL`` and the
  actor's email is denormalised into ``actor_label`` at write time, so history
  stays readable after an account is removed.
* **Never stores secrets.** ``context`` is scrubbed on the way in by the same
  redaction used for logs.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditAction(models.TextChoices):
    """Stable action identifiers. Add to this list; do not rename entries."""

    # --- Authentication
    LOGIN_SUCCEEDED = "auth.login.succeeded", _("Login succeeded")
    LOGIN_FAILED = "auth.login.failed", _("Login failed")
    LOGOUT = "auth.logout", _("Logout")
    SESSIONS_REVOKED = "auth.sessions.revoked", _("Sessions revoked")

    # --- Credentials. The tokens and passwords themselves are never recorded.
    PASSWORD_CHANGED = "auth.password.changed", _("Password changed")
    PASSWORD_RESET_REQUESTED = "auth.password.reset_requested", _("Password reset requested")
    PASSWORD_RESET_COMPLETED = "auth.password.reset_completed", _("Password reset completed")
    PASSWORD_RESET_FAILED = "auth.password.reset_failed", _("Password reset failed")
    EMAIL_VERIFICATION_REQUESTED = (
        "auth.email.verification_requested",
        _("Email verification requested"),
    )
    EMAIL_VERIFIED = "auth.email.verified", _("Email verified")
    EMAIL_VERIFICATION_FAILED = "auth.email.verification_failed", _("Email verification failed")

    # --- User administration
    USER_CREATED = "user.created", _("User created")
    USER_UPDATED = "user.updated", _("User updated")
    USER_ACTIVATED = "user.activated", _("User activated")
    USER_DEACTIVATED = "user.deactivated", _("User deactivated")
    USER_ROLE_CHANGED = "user.role_changed", _("User role changed")
    USER_EMAIL_CHANGED = "user.email_changed", _("User email address changed")
    USER_LISTED = "user.listed", _("User list viewed")
    PROFILE_IMAGE_UPDATED = "user.profile_image.updated", _("Profile image updated")
    PROFILE_IMAGE_REMOVED = "user.profile_image.removed", _("Profile image removed")

    # --- Domain profiles
    STUDENT_CREATED = "student.created", _("Student created")
    STUDENT_UPDATED = "student.updated", _("Student profile updated")
    STUDENT_FEE_STATUS_CHANGED = "student.fee_status.changed", _("Student fee status changed")
    TRAINER_CREATED = "trainer.created", _("Trainer created")
    TRAINER_UPDATED = "trainer.updated", _("Trainer profile updated")

    # --- Course catalogue and content
    CATEGORY_CREATED = "category.created", _("Category created")
    CATEGORY_UPDATED = "category.updated", _("Category updated")
    COURSE_CREATED = "course.created", _("Course created")
    COURSE_UPDATED = "course.updated", _("Course updated")
    COURSE_STATUS_CHANGED = "course.status.changed", _("Course status changed")
    COURSE_AUTHOR_ASSIGNED = "course.author.assigned", _("Course author assigned")
    COURSE_AUTHOR_REMOVED = "course.author.removed", _("Course author removed")
    COURSE_CONTENT_REORDERED = "course.content.reordered", _("Course content reordered")
    MODULE_CREATED = "module.created", _("Module created")
    MODULE_UPDATED = "module.updated", _("Module updated")
    MODULE_DELETED = "module.deleted", _("Module deleted")
    LESSON_CREATED = "lesson.created", _("Lesson created")
    LESSON_UPDATED = "lesson.updated", _("Lesson updated")
    LESSON_DELETED = "lesson.deleted", _("Lesson deleted")
    RESOURCE_UPLOADED = "resource.uploaded", _("Lesson resource uploaded")
    RESOURCE_DELETED = "resource.deleted", _("Lesson resource deleted")

    # --- Batches, schedules and enrolment
    BATCH_CREATED = "batch.created", _("Batch created")
    BATCH_UPDATED = "batch.updated", _("Batch updated")
    BATCH_STATUS_CHANGED = "batch.status.changed", _("Batch status changed")
    BATCH_TRAINER_ASSIGNED = "batch.trainer.assigned", _("Batch trainer assigned")
    SCHEDULE_CREATED = "schedule.created", _("Class schedule created")
    SCHEDULE_UPDATED = "schedule.updated", _("Class schedule updated")
    SCHEDULE_DELETED = "schedule.deleted", _("Class schedule deleted")
    ENROLLMENT_CREATED = "enrollment.created", _("Student enrolled")
    ENROLLMENT_STATUS_CHANGED = "enrollment.status.changed", _("Enrolment status changed")
    ENROLLMENT_SUSPENDED = "enrollment.suspended", _("Enrolment suspended")
    ENROLLMENT_CANCELLED = "enrollment.cancelled", _("Enrolment cancelled")
    ENROLLMENT_COMPLETED = "enrollment.completed", _("Enrolment completed")

    # --- Class sessions
    SESSIONS_GENERATED = "session.generated", _("Class sessions generated")
    SESSION_CREATED = "session.created", _("Class session created")
    SESSION_UPDATED = "session.updated", _("Class session updated")
    SESSION_STATUS_CHANGED = "session.status.changed", _("Class session status changed")
    SESSION_RESCHEDULED = "session.rescheduled", _("Class session rescheduled")

    # --- Attendance
    ATTENDANCE_MARKED = "attendance.marked", _("Attendance marked")
    ATTENDANCE_CORRECTED = "attendance.corrected", _("Attendance corrected")

    # --- Assignments
    ASSIGNMENT_CREATED = "assignment.created", _("Assignment created")
    ASSIGNMENT_UPDATED = "assignment.updated", _("Assignment updated")
    ASSIGNMENT_STATUS_CHANGED = "assignment.status.changed", _("Assignment status changed")
    ASSIGNMENT_DELETED = "assignment.deleted", _("Assignment deleted")
    ASSIGNMENT_ATTACHMENT_ADDED = "assignment.attachment.added", _("Assignment attachment added")
    ASSIGNMENT_ATTACHMENT_REMOVED = (
        "assignment.attachment.removed",
        _("Assignment attachment removed"),
    )
    SUBMISSION_CREATED = "submission.created", _("Assignment submitted")
    SUBMISSION_GRADED = "submission.graded", _("Assignment graded")
    SUBMISSION_RETURNED = "submission.returned", _("Assignment returned for rework")
    SUBMISSION_FILE_DOWNLOADED = "submission.file.downloaded", _("Submission file downloaded")

    # --- Assessments and results
    ASSESSMENT_CREATED = "assessment.created", _("Assessment created")
    ASSESSMENT_UPDATED = "assessment.updated", _("Assessment updated")
    ASSESSMENT_STATUS_CHANGED = "assessment.status.changed", _("Assessment status changed")
    ASSESSMENT_DELETED = "assessment.deleted", _("Assessment deleted")
    RESULT_RECORDED = "result.recorded", _("Result recorded")
    RESULT_UPDATED = "result.updated", _("Result updated")
    RESULT_IMPORT_PREVIEWED = "result.import.previewed", _("Result import previewed")
    RESULT_IMPORT_CONFIRMED = "result.import.confirmed", _("Result import confirmed")
    RESULT_IMPORT_REJECTED = "result.import.rejected", _("Result import rejected")

    # --- Academic configuration
    ACADEMIC_POLICY_UPDATED = "academic.policy.updated", _("Academic rules changed")

    # --- Projects
    PROJECT_CREATED = "project.created", _("Project created")
    PROJECT_UPDATED = "project.updated", _("Project updated")
    PROJECT_STATUS_CHANGED = "project.status.changed", _("Project status changed")
    PROJECT_DELETED = "project.deleted", _("Project deleted")
    PROJECT_ASSIGNED = "project.assigned", _("Project assigned to students")
    PROJECT_SUBMITTED = "project.submitted", _("Project deliverable submitted")
    PROJECT_REVIEWED = "project.reviewed", _("Project reviewed")
    PROJECT_FILE_DOWNLOADED = "project.file.downloaded", _("Project file downloaded")

    # --- Question bank
    QUESTION_CREATED = "question.created", _("Question created")
    QUESTION_UPDATED = "question.updated", _("Question updated")
    QUESTION_DELETED = "question.deleted", _("Question deleted")

    # --- Examinations
    EXAM_CREATED = "exam.created", _("Examination created")
    EXAM_UPDATED = "exam.updated", _("Examination updated")
    EXAM_STATUS_CHANGED = "exam.status.changed", _("Examination status changed")
    EXAM_ATTEMPT_STARTED = "exam.attempt.started", _("Examination attempt started")
    EXAM_ATTEMPT_SUBMITTED = "exam.attempt.submitted", _("Examination attempt submitted")
    EXAM_ATTEMPT_EXPIRED = "exam.attempt.expired", _("Examination attempt expired")
    EXAM_ATTEMPT_GRADED = "exam.attempt.graded", _("Examination attempt graded")
    EXAM_RESULTS_PUBLISHED = "exam.results.published", _("Examination results published")

    # --- Completion and certificates
    COMPLETION_ELIGIBLE = "completion.eligible", _("Student became completion-eligible")
    COMPLETION_APPROVED = "completion.approved", _("Course completion approved")
    COMPLETION_REJECTED = "completion.rejected", _("Course completion not approved")
    COMPLETION_REOPENED = "completion.reopened", _("Course completion reopened")
    CERTIFICATE_TEMPLATE_SAVED = "certificate.template.saved", _("Certificate template saved")
    CERTIFICATE_ISSUED = "certificate.issued", _("Certificate issued")
    CERTIFICATE_REISSUED = "certificate.reissued", _("Certificate reissued")
    CERTIFICATE_REVOKED = "certificate.revoked", _("Certificate revoked")
    CERTIFICATE_DOWNLOADED = "certificate.downloaded", _("Certificate downloaded")
    CERTIFICATE_VERIFIED = "certificate.verified", _("Certificate verified publicly")

    # --- Communication
    ANNOUNCEMENT_CREATED = "announcement.created", _("Announcement created")
    ANNOUNCEMENT_UPDATED = "announcement.updated", _("Announcement updated")
    ANNOUNCEMENT_PUBLISHED = "announcement.published", _("Announcement published")
    ANNOUNCEMENT_ARCHIVED = "announcement.archived", _("Announcement archived")
    THREAD_CREATED = "discussion.thread.created", _("Discussion thread started")
    THREAD_MODERATED = "discussion.thread.moderated", _("Discussion thread moderated")
    REPLY_CREATED = "discussion.reply.created", _("Discussion reply posted")
    REPLY_HIDDEN = "discussion.reply.hidden", _("Discussion reply hidden")

    # --- Reporting and data tools
    REPORT_EXPORTED = "report.exported", _("Report exported")
    BULK_IMPORT_PREVIEWED = "data.import.previewed", _("Bulk import previewed")
    BULK_IMPORT_CONFIRMED = "data.import.confirmed", _("Bulk import confirmed")
    BULK_IMPORT_REJECTED = "data.import.rejected", _("Bulk import discarded")

    # --- File security
    UPLOAD_REJECTED = "file.upload.rejected", _("Upload rejected by a security check")

    # --- Authorization
    PERMISSION_DENIED = "authz.denied", _("Permission denied")


class AuditResult(models.TextChoices):
    SUCCESS = "success", _("Success")
    FAILURE = "failure", _("Failure")
    DENIED = "denied", _("Denied")


class AuditLogQuerySet(models.QuerySet):
    def delete(self):
        raise PermissionError("Audit records are append-only and cannot be deleted.")

    def update(self, **kwargs):
        raise PermissionError("Audit records are append-only and cannot be modified.")

    def purge_before(self, cutoff):
        """Retention trimming — the only supported removal path.

        Kept separate from ``delete`` so removing history is always explicit
        and greppable.
        """
        return super().filter(created_at__lt=cutoff).delete()


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
        help_text=_("Null for anonymous or system actions."),
    )
    actor_label = models.CharField(
        max_length=254,
        blank=True,
        help_text=_("Actor identity captured at write time; survives account deletion."),
    )
    action = models.CharField(max_length=64, choices=AuditAction.choices, db_index=True)
    resource_type = models.CharField(max_length=64, blank=True, db_index=True)
    resource_id = models.CharField(max_length=64, blank=True, db_index=True)
    result = models.CharField(
        max_length=16, choices=AuditResult.choices, default=AuditResult.SUCCESS
    )

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=255, blank=True)

    context = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Extra non-sensitive detail. Scrubbed of secrets on write."),
    )

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log entries")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["resource_type", "resource_id"], name="audit_resource_idx"),
            models.Index(fields=["actor", "-created_at"], name="audit_actor_time_idx"),
            models.Index(fields=["action", "-created_at"], name="audit_action_time_idx"),
        ]

    def __str__(self) -> str:
        actor = self.actor_label or "anonymous"
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.action} by {actor}"

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            raise PermissionError("Audit records are append-only and cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit records are append-only and cannot be deleted.")
