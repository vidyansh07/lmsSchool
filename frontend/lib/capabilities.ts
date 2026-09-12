/**
 * Capability names, mirroring `apps/accounts/roles.py`.
 *
 * These drive what the interface *offers*. They are never a security control:
 * the backend re-checks every capability on every request, so hiding a button
 * is a courtesy to the user, not a defence against an attacker.
 */
export const Capability = {
  userViewAny: 'user.view_any',
  userCreate: 'user.create',
  userUpdateAny: 'user.update_any',
  userSetActive: 'user.set_active',
  userChangeRole: 'user.change_role',
  profileViewOwn: 'profile.view_own',
  profileUpdateOwn: 'profile.update_own',
  studentViewAny: 'student.view_any',
  studentCreate: 'student.create',
  studentUpdateAny: 'student.update_any',
  studentSetFeeStatus: 'student.set_fee_status',
  feeViewAny: 'fee.view_any',
  feeManageAny: 'fee.manage_any',
  trainerViewAny: 'trainer.view_any',
  trainerCreate: 'trainer.create',
  trainerUpdateAny: 'trainer.update_any',
  categoryManage: 'category.manage',
  courseViewAny: 'course.view_any',
  courseCreate: 'course.create',
  courseUpdateAny: 'course.update_any',
  coursePublishAny: 'course.publish_any',
  courseAssignAuthors: 'course.assign_authors',
  batchViewAny: 'batch.view_any',
  batchCreate: 'batch.create',
  batchUpdateAny: 'batch.update_any',
  batchManageSchedule: 'batch.manage_schedule',
  enrolmentViewAny: 'enrolment.view_any',
  enrolmentCreate: 'enrolment.create',
  enrolmentUpdateAny: 'enrolment.update_any',
  platformConfigure: 'platform.configure',
  auditView: 'audit.view',
  recordViewDeleted: 'record.view_deleted',
  recordRestore: 'record.restore',
  recordPurge: 'record.purge',
  academicConfigure: 'academic.configure',
  sessionManageAny: 'session.manage_any',
  attendanceCorrectAny: 'attendance.correct_any',
  attendanceViewAny: 'attendance.view_any',
  dsrViewAny: 'dsr.view_any',
  dsrManageAny: 'dsr.manage_any',
  dsrReview: 'dsr.review',
  performanceViewAny: 'performance.view_any',
  reviewManageAny: 'review.manage_any',
  assignmentViewAny: 'assignment.view_any',
  assignmentManageAny: 'assignment.manage_any',
  assignmentGradeAny: 'assignment.grade_any',
  assessmentViewAny: 'assessment.view_any',
  assessmentManageAny: 'assessment.manage_any',
  resultManageAny: 'result.manage_any',
  projectViewAny: 'project.view_any',
  projectManageAny: 'project.manage_any',
  projectReviewAny: 'project.review_any',
  questionViewAny: 'question.view_any',
  questionManageAny: 'question.manage_any',
  examViewAny: 'exam.view_any',
  examManageAny: 'exam.manage_any',
  examGradeAny: 'exam.grade_any',
  completionViewAny: 'completion.view_any',
  completionApprove: 'completion.approve',
  certificateManage: 'certificate.manage',
  announcementManageAny: 'announcement.manage_any',
  discussionModerateAny: 'discussion.moderate_any',
  reportViewAny: 'report.view_any',
  dataExport: 'data.export',
  dataImport: 'data.import',
  exportViewAny: 'export.view_any',
} as const;

export type CapabilityName = (typeof Capability)[keyof typeof Capability];

export function can(
  capabilities: string[] | undefined,
  capability: CapabilityName,
): boolean {
  return Boolean(capabilities?.includes(capability));
}
