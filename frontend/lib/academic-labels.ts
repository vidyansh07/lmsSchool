/** Display labels and badge variants for the Phase 4 vocabulary. */

import type {
  AcademicLifecycle,
  AssessmentCategory,
  AssessmentDelivery,
  AttendanceStatus,
  ImportStatus,
  SessionStatus,
  SubmissionKind,
  SubmissionStatus,
} from '@/types/api';

/** The badge vocabulary in `components/ui/badge.tsx`. */
type Variant = 'neutral' | 'success' | 'warning' | 'error';

export const SESSION_STATUS_LABEL: Record<SessionStatus, string> = {
  scheduled: 'Scheduled',
  in_progress: 'In progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
  rescheduled: 'Rescheduled',
};

export const SESSION_STATUS_VARIANT: Record<SessionStatus, Variant> = {
  scheduled: 'neutral',
  in_progress: 'warning',
  completed: 'success',
  cancelled: 'error',
  rescheduled: 'neutral',
};

export const ATTENDANCE_STATUS_LABEL: Record<AttendanceStatus, string> = {
  present: 'Present',
  absent: 'Absent',
  late: 'Late',
  excused: 'Excused',
};

export const ATTENDANCE_STATUS_VARIANT: Record<AttendanceStatus, Variant> = {
  present: 'success',
  absent: 'error',
  late: 'warning',
  excused: 'neutral',
};

export const ATTENDANCE_OPTIONS: { value: AttendanceStatus; label: string }[] = (
  Object.keys(ATTENDANCE_STATUS_LABEL) as AttendanceStatus[]
).map((value) => ({ value, label: ATTENDANCE_STATUS_LABEL[value] }));

export const LIFECYCLE_LABEL: Record<AcademicLifecycle, string> = {
  draft: 'Draft',
  published: 'Published',
  closed: 'Closed',
  archived: 'Archived',
};

export const LIFECYCLE_VARIANT: Record<AcademicLifecycle, Variant> = {
  draft: 'neutral',
  published: 'success',
  closed: 'warning',
  archived: 'neutral',
};

export const SUBMISSION_KIND_LABEL: Record<SubmissionKind, string> = {
  file: 'File upload',
  text: 'Written answer',
  link: 'Link',
  any: 'File, text or link',
};

export const SUBMISSION_STATUS_LABEL: Record<SubmissionStatus, string> = {
  submitted: 'Submitted',
  graded: 'Graded',
  returned: 'Returned for rework',
};

export const SUBMISSION_STATUS_VARIANT: Record<SubmissionStatus, Variant> = {
  submitted: 'neutral',
  graded: 'success',
  returned: 'warning',
};

export const ASSESSMENT_CATEGORY_LABEL: Record<AssessmentCategory, string> = {
  weekly_test: 'Weekly test',
  practice: 'Practice test',
  mock: 'Mock test',
  other: 'Other assessment',
};

export const ASSESSMENT_DELIVERY_LABEL: Record<AssessmentDelivery, string> = {
  external_link: 'External link',
  file_upload: 'File upload',
  offline: 'Offline / in class',
};

export const IMPORT_STATUS_LABEL: Record<ImportStatus, string> = {
  preview: 'Awaiting confirmation',
  confirmed: 'Applied',
  rejected: 'Discarded',
  failed: 'Failed validation',
};

export const IMPORT_STATUS_VARIANT: Record<ImportStatus, Variant> = {
  preview: 'warning',
  confirmed: 'success',
  rejected: 'neutral',
  failed: 'error',
};

/** A date and time in the reader's locale, or an em dash when there is none. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

/** `09:00` from `09:00:00`. */
export function formatTime(value: string): string {
  return value.slice(0, 5);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// --- Phase 5 ---------------------------------------------------------------

export const PROJECT_KIND_LABEL: Record<import('@/types/api').ProjectKind, string> = {
  small: 'Small project',
  major: 'Major project',
  capstone: 'Capstone project',
};

export const PROJECT_WORK_LABEL: Record<import('@/types/api').ProjectWorkStatus, string> = {
  assigned: 'Assigned',
  in_progress: 'In progress',
  submitted: 'Submitted',
  under_review: 'Under review',
  rework: 'Rework requested',
  approved: 'Approved',
  completed: 'Completed',
};

export const PROJECT_WORK_VARIANT: Record<import('@/types/api').ProjectWorkStatus, Variant> = {
  assigned: 'neutral',
  in_progress: 'neutral',
  submitted: 'warning',
  under_review: 'warning',
  rework: 'error',
  approved: 'success',
  completed: 'success',
};

export const QUESTION_TYPE_LABEL: Record<import('@/types/api').QuestionType, string> = {
  mcq: 'Multiple choice, one answer',
  multiple: 'Multiple choice, several answers',
  true_false: 'True or false',
  short_answer: 'Short answer',
  long_answer: 'Long answer',
  file: 'File upload',
};

export const DIFFICULTY_LABEL: Record<import('@/types/api').Difficulty, string> = {
  easy: 'Easy',
  medium: 'Medium',
  hard: 'Hard',
};

export const ATTEMPT_STATUS_LABEL: Record<import('@/types/api').AttemptStatus, string> = {
  in_progress: 'In progress',
  submitted: 'Submitted, awaiting marking',
  graded: 'Graded',
  expired: 'Time expired',
};

export const ATTEMPT_STATUS_VARIANT: Record<import('@/types/api').AttemptStatus, Variant> = {
  in_progress: 'warning',
  submitted: 'neutral',
  graded: 'success',
  expired: 'error',
};

/** `12:05` from 725 seconds. The value itself always comes from the server. */
export function formatCountdown(seconds: number): string {
  const safe = Math.max(0, seconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const remainder = safe % 60;
  const pad = (value: number) => String(value).padStart(2, '0');
  return hours > 0
    ? `${hours}:${pad(minutes)}:${pad(remainder)}`
    : `${pad(minutes)}:${pad(remainder)}`;
}

// --- Phase 6 ---------------------------------------------------------------

export const DELIVERY_MODE_LABEL: Record<import('@/types/api').DeliveryMode, string> = {
  offline: 'In the classroom',
  online: 'Online',
  hybrid: 'Both',
};

export const COMPLETION_STATUS_LABEL: Record<import('@/types/api').CompletionStatus, string> = {
  in_progress: 'In progress',
  eligible: 'Eligible, awaiting approval',
  approved: 'Completed',
  rejected: 'Not approved',
};

export const COMPLETION_STATUS_VARIANT: Record<import('@/types/api').CompletionStatus, Variant> = {
  in_progress: 'neutral',
  eligible: 'warning',
  approved: 'success',
  rejected: 'error',
};

export const CERTIFICATE_STATUS_LABEL: Record<import('@/types/api').CertificateStatus, string> = {
  issued: 'Issued',
  revoked: 'Revoked',
  superseded: 'Superseded',
};

export const CERTIFICATE_STATUS_VARIANT: Record<
  import('@/types/api').CertificateStatus,
  Variant
> = {
  issued: 'success',
  revoked: 'error',
  superseded: 'neutral',
};

/** A date without a time, for completion and issue dates. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, { dateStyle: 'medium' });
}
