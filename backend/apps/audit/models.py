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

    # --- Session inventory (ERP Phase 6, ADR-06). Distinct from
    # `SESSIONS_REVOKED` above, which is the pre-existing "sign out
    # everywhere" bulk action; these cover the per-session endpoints.
    SESSION_REVOKED = "session.revoked", _("Session revoked")
    SESSION_REVOKED_BY_ADMIN = "session.revoked_by_admin", _("Session revoked by an administrator")
    SESSION_NEW_DEVICE_DETECTED = "session.new_device_detected", _("New device detected at sign-in")

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

    # --- Roles as rows (ERP Phase 1)
    ROLE_CREATED = "role.created", _("Role created")
    ROLE_UPDATED = "role.updated", _("Role updated")
    ROLE_DELETED = "role.deleted", _("Role deleted")
    PERMISSIONS_SYNCED = "permission.synced", _("Permission catalog synchronised")
    PERMISSION_LOCKED = "permission.locked", _("Permission grant locked")
    PERMISSION_UNLOCKED = "permission.unlocked", _("Permission grant unlocked")
    SCOPE_GRANTED = "scope.granted", _("Batch or course scope granted")
    SCOPE_REVOKED = "scope.revoked", _("Batch or course scope revoked")

    # --- Policy management (ERP Phase 3, ADR-04)
    POLICY_UPDATED = "policy.updated", _("Policy changed")
    POLICY_RESET = "policy.reset", _("Policy reset to its default")
    STEP_UP_SUCCEEDED = "auth.step_up.succeeded", _("Step-up authentication succeeded")
    STEP_UP_FAILED = "auth.step_up.failed", _("Step-up authentication failed")

    # --- Email one-time codes (ERP Phase 4, ADR-05). Never carry the code.
    OTP_SENT = "otp.sent", _("One-time code sent")
    OTP_VERIFIED = "otp.verified", _("One-time code verified")
    OTP_FAILED = "otp.failed", _("One-time code verification failed")
    OTP_THROTTLED = "otp.throttled", _("One-time code request throttled")

    # --- MFA: TOTP and recovery codes (ERP Phase 5, ADR-05). Never the
    # secret, the code, or a recovery code — see apps.accounts.mfa.
    LOGIN_PENDING = "auth.login.pending", _("Sign-in pending MFA")
    MFA_ENROLLED = "mfa.enrolled", _("MFA enabled")
    MFA_CONFIRMED = "mfa.confirmed", _("MFA device confirmed")
    MFA_DISABLED = "mfa.disabled", _("MFA disabled")
    MFA_VERIFIED = "mfa.verified", _("MFA code verified")
    MFA_FAILED = "mfa.failed", _("MFA code verification failed")
    MFA_RECOVERY_USED = "mfa.recovery_used", _("Recovery code used")
    MFA_RECOVERY_REGENERATED = "mfa.recovery_regenerated", _("Recovery codes regenerated")

    # --- Domain profiles
    STUDENT_CREATED = "student.created", _("Student created")
    STUDENT_UPDATED = "student.updated", _("Student profile updated")
    STUDENT_FEE_STATUS_CHANGED = "student.fee_status.changed", _("Student fee status changed")
    STUDENT_FEE_AMOUNT_CHANGED = "student.fee_amount.changed", _("Student fee amount changed")
    # ERP Phase 17: no new schema on `StudentProfile` for the duplicate-check
    # override — a reason typed at registration, when a possible existing
    # student was shown and the counsellor said "this is a different
    # person". Audit-only, written by `apps.students.services.create_student`
    # at the point registration actually proceeds past a matched duplicate.
    STUDENT_DUPLICATE_OVERRIDDEN = (
        "student.duplicate_overridden",
        _("Registered past a possible duplicate match"),
    )
    FEE_PLAN_SET = "fee.plan.set", _("Fee agreed")
    FEE_PLAN_UPDATED = "fee.plan.updated", _("Fee changed")
    FEE_NEXT_DUE_SET = "fee.next_due.set", _("Next payment expected")
    FEE_PAYMENT_RECORDED = "fee.payment.recorded", _("Payment recorded")
    FEE_PAYMENT_VOIDED = "fee.payment.voided", _("Payment voided")
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
    BATCH_TIMETABLE_SET = "batch.timetable.set", _("Batch timetable set up")
    SCHEDULE_CREATED = "schedule.created", _("Class schedule created")
    SCHEDULE_UPDATED = "schedule.updated", _("Class schedule updated")
    SCHEDULE_DELETED = "schedule.deleted", _("Class schedule deleted")
    ENROLLMENT_CREATED = "enrollment.created", _("Student enrolled")
    ENROLLMENT_STATUS_CHANGED = "enrollment.status.changed", _("Enrolment status changed")
    ENROLLMENT_SUSPENDED = "enrollment.suspended", _("Enrolment suspended")
    ENROLLMENT_CANCELLED = "enrollment.cancelled", _("Enrolment cancelled")
    ENROLLMENT_COMPLETED = "enrollment.completed", _("Enrolment completed")
    ENROLLMENT_TRANSFERRED = "enrollment.transferred", _("Student transferred to another batch")
    ENROLLMENT_UPGRADED = "enrollment.upgraded", _("Student upgraded to another batch")

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

    # --- Appearance
    BRANDING_UPDATED = "branding.updated", _("Branding changed")

    # --- Academic configuration
    ACADEMIC_POLICY_UPDATED = "academic.policy.updated", _("Academic rules changed")

    # --- Institution settings
    SYSTEM_SETTINGS_UPDATED = "settings.updated", _("Institution settings changed")

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

    # --- Daily status reports
    DSR_CREATED = "dsr.created", _("Daily status report started")
    DSR_UPDATED = "dsr.updated", _("Daily status report updated")
    DSR_SUBMITTED = "dsr.submitted", _("Daily status report submitted")
    DSR_REVIEW_STARTED = "dsr.review.started", _("Daily status report under review")
    DSR_APPROVED = "dsr.approved", _("Daily status report approved")
    DSR_REJECTED = "dsr.rejected", _("Daily status report rejected")
    DSR_REVISION_REQUESTED = "dsr.revision_requested", _("Daily status report returned")

    # --- Trainer requirements
    REQUIREMENT_RAISED = "requirement.raised", _("Trainer requirement raised")
    REQUIREMENT_REPLIED = "requirement.replied", _("Trainer requirement answered")
    REQUIREMENT_CLOSED = "requirement.closed", _("Trainer requirement closed")

    # --- Course timeline
    SESSION_TOPIC_PLANNED = "session.topic.planned", _("Class topic planned")
    SESSION_TOPIC_RECORDED = "session.topic.recorded", _("Class topic recorded as taught")

    # --- Performance and reviews
    REVIEW_RECORDED = "review.recorded", _("Performance review recorded")
    REVIEW_UPDATED = "review.updated", _("Performance review updated")
    FEEDBACK_RECORDED = "feedback.recorded", _("Feedback recorded")
    RISK_THRESHOLDS_UPDATED = "risk.thresholds.updated", _("Risk thresholds changed")
    RISK_RECOMPUTED = "risk.recomputed", _("Risk recomputed")

    # --- Exports as background jobs
    EXPORT_QUEUED = "export.queued", _("Export queued")
    EXPORT_COMPLETED = "export.completed", _("Export completed")
    EXPORT_FAILED = "export.failed", _("Export failed")
    EXPORT_DOWNLOADED = "export.downloaded", _("Export downloaded")
    EXPORT_CANCELLED = "export.cancelled", _("Export cancelled")
    EXPORT_EXPIRED = "export.expired", _("Export expired")

    # --- Reversible deletion
    #
    # One vocabulary for every model, because "who removed this and can we get
    # it back?" is the same question whichever table it is asked about.
    RECORD_DELETED = "record.deleted", _("Record deleted")
    RECORD_RESTORED = "record.restored", _("Record restored")
    RECORD_PURGED = "record.purged", _("Record destroyed permanently")

    # --- File security
    UPLOAD_REJECTED = "file.upload.rejected", _("Upload rejected by a security check")

    # --- Authorization
    PERMISSION_DENIED = "authz.denied", _("Permission denied")

    # --- Organisation
    #
    # Moving somebody between centres is its own event rather than a field
    # change on `user.updated`: it is the one edit that changes what a person
    # can see rather than what they are, and it should be findable with a
    # single query.
    BRANCH_CREATED = "branch.created", _("Branch created")
    BRANCH_UPDATED = "branch.updated", _("Branch updated")
    USER_BRANCH_CHANGED = "user.branch_changed", _("Account moved between branches")

    # --- Dynamic forms (ERP Phase 8)
    #
    # `form.version_created`, `form.published` and `form.unpublished` are the
    # three the phase's API contract names explicitly.
    # `form.definition_created` and `form.fields_replaced` are added
    # alongside them so every state change is audited (rule 5), not just the
    # three the contract calls out by name.
    FORM_DEFINITION_CREATED = "form.definition_created", _("Form definition created")
    FORM_VERSION_CREATED = "form.version_created", _("Form version created")
    FORM_FIELDS_REPLACED = "form.fields_replaced", _("Form version's fields replaced")
    FORM_PUBLISHED = "form.published", _("Form version published")
    FORM_UNPUBLISHED = "form.unpublished", _("Form version unpublished")

    # --- Activity engine (ERP Phase 9)
    #
    # `activity.created`, `activity.completed` and `activity.reviewed` are
    # the three `API_CONTRACTS.md` names explicitly; `activity.transitioned`
    # covers every other lifecycle move (plan, assign, start, cancel,
    # reopen — including the system-driven OVERDUE/MISSED ones, actor null)
    # so every state change is audited (rule 5), and `activity_type.*` cover
    # the catalog's own CRUD.
    ACTIVITY_TYPE_CREATED = "activity_type.created", _("Activity type created")
    ACTIVITY_TYPE_UPDATED = "activity_type.updated", _("Activity type updated")
    ACTIVITY_CREATED = "activity.created", _("Activity created")
    ACTIVITY_TRANSITIONED = "activity.transitioned", _("Activity status changed")
    ACTIVITY_COMPLETED = "activity.completed", _("Activity completed")
    ACTIVITY_REVIEWED = "activity.reviewed", _("Activity reviewed")
    ACTIVITY_DELETED = "activity.deleted", _("Activity deleted")

    # --- Search and saved filters (ERP Phase 11)
    #
    # `context` on `SEARCH_PERFORMED` is counts only (types requested, hits
    # per type) — never the query text or the ids it matched. A free-text
    # search box can carry anything a caller chose to type, including
    # something they should not have, and an audit row is readable by anyone
    # holding `audit.view`; the query itself is exactly the "under any key
    # name" case the secrets rule already gives OTPs and TOTP secrets.
    SEARCH_PERFORMED = "search.performed", _("Global search performed")
    SAVED_FILTER_CREATED = "saved_filter.created", _("Saved filter created")
    SAVED_FILTER_DELETED = "saved_filter.deleted", _("Saved filter deleted")

    # --- Automation (ERP Phase 14, ADR-13)
    #
    # `automation.ran`/`automation.skipped`/`automation.failed` are the
    # catalog's own three per-run outcomes (`AUTOMATION_CATALOG.md`
    # "Guards"); `automation.rule_*` cover the builder's own CRUD so every
    # state change on the rule itself is audited too (rule 5).
    AUTOMATION_RULE_CREATED = "automation.rule_created", _("Automation rule created")
    AUTOMATION_RULE_UPDATED = "automation.rule_updated", _("Automation rule updated")
    AUTOMATION_RULE_ACTIVATED = "automation.rule_activated", _("Automation rule activated")
    AUTOMATION_RULE_PAUSED = "automation.rule_paused", _("Automation rule paused")
    AUTOMATION_RULE_DELETED = "automation.rule_deleted", _("Automation rule deleted")
    AUTOMATION_RAN = "automation.ran", _("Automation rule ran")
    AUTOMATION_SKIPPED = "automation.skipped", _("Automation run skipped")
    AUTOMATION_FAILED = "automation.failed", _("Automation run failed")

    # --- Communication centre (ERP Phase 19, ADR-12)
    #
    # Template lifecycle mirrors Phase 8's own form-version events
    # (`form.version_created`/`form.published`) so "who changed this
    # template, and when was it published" reads the same way for both.
    # `communication.sent` carries counts only, never recipient PII (the
    # same reasoning `search.performed` already documents). Delivery state
    # changes made from the outside (the WhatsApp webhook) are audited too,
    # with no human actor, because a state change is a state change (rule 5)
    # regardless of who — or what — triggered it.
    TEMPLATE_CREATED = "template.created", _("Message template created")
    TEMPLATE_VERSION_CREATED = "template.version_created", _("Template version created")
    TEMPLATE_VERSION_UPDATED = "template.version_updated", _("Template version updated")
    TEMPLATE_APPROVED = "template.approved", _("Template version approved")
    TEMPLATE_PUBLISHED = "template.published", _("Template version published")
    TEMPLATE_TEST_SENT = "template.test_sent", _("Template test message sent")
    COMMUNICATION_SENT = "communication.sent", _("Manual communication sent")
    DELIVERY_RETRIED = "delivery.retried", _("Delivery retried")
    DELIVERY_CANCELLED = "delivery.cancelled", _("Delivery cancelled")
    DELIVERY_WEBHOOK_UPDATED = "delivery.webhook_updated", _("Delivery updated by provider webhook")
    ANNOUNCEMENT_SCHEDULED = "announcement.scheduled", _("Announcement scheduled")
    ANNOUNCEMENT_CANCELLED = "announcement.cancelled", _("Scheduled announcement cancelled")


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
