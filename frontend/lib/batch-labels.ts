/** Display labels for batch, enrolment and calendar enumerations. */

import type { BatchStatus, CalendarEventKind, EnrollmentStatus, Weekday } from '@/types/api';

export const BATCH_STATUS_LABEL: Record<BatchStatus, string> = {
  upcoming: 'Upcoming',
  active: 'Active',
  completed: 'Completed',
  cancelled: 'Cancelled',
  archived: 'Archived',
};

export const BATCH_STATUS_VARIANT: Record<
  BatchStatus,
  'neutral' | 'success' | 'warning' | 'error'
> = {
  upcoming: 'warning',
  active: 'success',
  completed: 'neutral',
  cancelled: 'error',
  archived: 'neutral',
};

export const BATCH_STATUS_OPTIONS = (
  Object.keys(BATCH_STATUS_LABEL) as BatchStatus[]
).map((value) => ({ value, label: BATCH_STATUS_LABEL[value] }));

export const ENROLLMENT_STATUS_LABEL: Record<EnrollmentStatus, string> = {
  pending: 'Pending',
  active: 'Active',
  suspended: 'Suspended',
  completed: 'Completed',
  cancelled: 'Cancelled',
  // The sixth `EnrollmentStatus` (`apps.enrollments.models`) the backend has
  // always had and this map never did, which is why a real transferred row
  // rendered a blank STATUS cell on `/admissions` and could not be filtered
  // for: `ENROLLMENT_STATUS_OPTIONS` is derived from these keys.
  // Shortened from the backend's "Transferred to another batch" because this
  // string is a badge in a table column; the batch it moved to is on the
  // student's own timeline, not in the cell.
  transferred: 'Transferred',
};

export const ENROLLMENT_STATUS_VARIANT: Record<
  EnrollmentStatus,
  'neutral' | 'success' | 'warning' | 'error'
> = {
  pending: 'warning',
  active: 'success',
  suspended: 'warning',
  completed: 'neutral',
  cancelled: 'error',
  // Neutral, not `error`: colour means state, and "moved to another batch" is
  // a fact about where the student is, not something that went wrong. The
  // backend keeps it apart from `cancelled` for exactly that reason.
  transferred: 'neutral',
};

export const ENROLLMENT_STATUS_OPTIONS = (
  Object.keys(ENROLLMENT_STATUS_LABEL) as EnrollmentStatus[]
).map((value) => ({ value, label: ENROLLMENT_STATUS_LABEL[value] }));

/** 0 = Monday, matching the API. */
export const WEEKDAY_LABEL: Record<Weekday, string> = {
  0: 'Monday',
  1: 'Tuesday',
  2: 'Wednesday',
  3: 'Thursday',
  4: 'Friday',
  5: 'Saturday',
  6: 'Sunday',
};

export const WEEKDAY_OPTIONS = ([0, 1, 2, 3, 4, 5, 6] as Weekday[]).map((value) => ({
  value,
  label: WEEKDAY_LABEL[value],
}));

export const EVENT_KIND_LABEL: Record<CalendarEventKind, string> = {
  class: 'Class',
  batch_start: 'Batch starts',
  batch_end: 'Batch ends',
  course_start: 'Course starts',
  course_end: 'Course ends',
  assignment_due: 'Assignment due',
  project_due: 'Project due',
  quiz: 'Quiz',
  exam: 'Exam',
  announcement: 'Announcement',
  // `apps.dashboards.calendar.EventKind.ACTIVITY_DUE`, registered as a source
  // in ERP Phase 9 and never labelled here — so eighteen of a manager's
  // twenty-seven calendar rows read the raw enum `activity_due` in their badge.
  activity_due: 'Activity due',
};

/** "09:00" from the API's "09:00:00". */
export function formatTime(value: string | null | undefined): string {
  if (!value) return '';
  return value.slice(0, 5);
}

/** "Mon 3 Mar" from an ISO datetime. */
export function formatEventDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

export function formatEventTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** Today's date as an ISO day string, for calendar queries. */
export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function isoDaysFromNow(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}
