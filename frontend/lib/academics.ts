/** API calls for class sessions, attendance and the academic rules (Phase 4). */

import { apiFetch, apiMutate, queryString } from './api';
import type {
  AcademicPolicy,
  AttendanceStatus,
  ClassSession,
  EffectivePolicy,
  MarkResult,
  MyAttendance,
  Paginated,
  Register,
  SessionStatus,
} from '@/types/api';

// --- Class sessions --------------------------------------------------------

export interface SessionQuery {
  batch?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  ordering?: string;
  [key: string]: string | number | undefined;
}

export async function listSessions(query: SessionQuery = {}): Promise<Paginated<ClassSession>> {
  return apiFetch<Paginated<ClassSession>>(`/api/v1/sessions/${queryString(query)}`);
}

/** The trainer's daily driver: every class they teach today. */
export async function listTodaySessions(): Promise<ClassSession[]> {
  return apiFetch<ClassSession[]>('/api/v1/sessions/today/');
}

export async function getSession(id: string): Promise<ClassSession> {
  return apiFetch<ClassSession>(`/api/v1/sessions/${id}/`);
}

export async function generateSessions(
  batchId: string,
  window: { start?: string; end?: string } = {},
): Promise<{
  created: number;
  skipped: number;
  /** Days inside a holiday on the academic calendar. Reported so an empty week
   *  has an explanation rather than looking like a generation failure. */
  on_holiday: number;
  start: string;
  end: string;
}> {
  return apiMutate(`/api/v1/batches/${batchId}/sessions/generate/`, {
    method: 'POST',
    body: window,
  });
}

export async function setSessionStatus(
  id: string,
  status: SessionStatus,
  reason = '',
): Promise<ClassSession> {
  return apiMutate<ClassSession>(`/api/v1/sessions/${id}/status/`, {
    method: 'POST',
    body: { status, reason },
  });
}

/** Where a class's *topic* is, distinct from where the class itself is
 *  (`SessionStatus`) — mirrors `apps.sessions.models.TopicStatus`. */
export type SessionTopicStatus = 'planned' | 'in_progress' | 'completed' | 'skipped' | 'rescheduled';

/**
 * Record what a class actually covered against the curriculum — or, with no
 * `lesson_id`, that nothing was (`status: 'skipped'`). Distinct from
 * `setSessionStatus`: that asks "did the class happen?"; this asks "what did
 * it cover?", and a class can be `completed` while its topic is `skipped`
 * (revision, a test, nothing new taught).
 */
export async function recordSessionTopic(
  id: string,
  payload: { lesson_id?: string | null; status?: SessionTopicStatus },
): Promise<ClassSession> {
  return apiMutate<ClassSession>(`/api/v1/sessions/${id}/topic/`, {
    method: 'POST',
    body: payload,
  });
}

// --- Attendance ------------------------------------------------------------

export async function getRegister(sessionId: string): Promise<Register> {
  return apiFetch<Register>(`/api/v1/sessions/${sessionId}/register/`);
}

/**
 * Save a whole register in one request.
 *
 * Bulk on purpose, matching the backend: a trainer marks the room in one
 * action, and a half-saved register is worse than none.
 */
export async function markAttendance(
  sessionId: string,
  entries: { enrollment_id: string; status: AttendanceStatus; note?: string }[],
): Promise<MarkResult> {
  return apiMutate<MarkResult>(`/api/v1/sessions/${sessionId}/register/`, {
    method: 'POST',
    body: { entries },
  });
}

export async function listMyAttendance(): Promise<MyAttendance[]> {
  return apiFetch<MyAttendance[]>('/api/v1/attendance/mine/');
}

// --- Academic rules --------------------------------------------------------

export async function getEffectivePolicy(courseId?: string): Promise<EffectivePolicy> {
  return apiFetch<EffectivePolicy>(
    `/api/v1/academics/policy/effective/${queryString({ course: courseId })}`,
  );
}

export async function getGlobalPolicy(): Promise<AcademicPolicy> {
  return apiFetch<AcademicPolicy>('/api/v1/academics/policy/');
}

export async function updateGlobalPolicy(
  changes: Record<string, unknown>,
): Promise<AcademicPolicy> {
  return apiMutate<AcademicPolicy>('/api/v1/academics/policy/', {
    method: 'PATCH',
    body: changes,
  });
}

export async function getCoursePolicy(courseId: string): Promise<AcademicPolicy> {
  return apiFetch<AcademicPolicy>(`/api/v1/academics/policy/courses/${courseId}/`);
}

export async function updateCoursePolicy(
  courseId: string,
  changes: Record<string, unknown>,
): Promise<AcademicPolicy> {
  return apiMutate<AcademicPolicy>(`/api/v1/academics/policy/courses/${courseId}/`, {
    method: 'PATCH',
    body: changes,
  });
}

export async function clearCoursePolicy(courseId: string): Promise<void> {
  await apiMutate<void>(`/api/v1/academics/policy/courses/${courseId}/`, { method: 'DELETE' });
}
