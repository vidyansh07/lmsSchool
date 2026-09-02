/** API calls for assignments and submissions (Phase 4.3/4.4). */

import { apiBaseUrl } from './env';
import { apiFetch, apiMutate, queryString } from './api';
import type {
  Assignment,
  AcademicLifecycle,
  Paginated,
  StaffSubmission,
  StudentAssignment,
  Submission,
} from '@/types/api';

export interface AssignmentQuery {
  course?: string;
  batch?: string;
  status?: string;
  search?: string;
  page?: number;
  ordering?: string;
  [key: string]: string | number | undefined;
}

export async function listAssignments(
  query: AssignmentQuery = {},
): Promise<Paginated<Assignment>> {
  return apiFetch<Paginated<Assignment>>(`/api/v1/assignments/${queryString(query)}`);
}

export async function listMyAssignments(
  query: AssignmentQuery = {},
): Promise<Paginated<StudentAssignment>> {
  return apiFetch<Paginated<StudentAssignment>>(`/api/v1/assignments/mine/${queryString(query)}`);
}

export async function getAssignment(id: string): Promise<Assignment> {
  return apiFetch<Assignment>(`/api/v1/assignments/${id}/`);
}

export async function getStudentAssignment(id: string): Promise<StudentAssignment> {
  return apiFetch<StudentAssignment>(`/api/v1/assignments/${id}/`);
}

export async function createAssignment(
  courseId: string,
  payload: Record<string, unknown>,
): Promise<Assignment> {
  return apiMutate<Assignment>(`/api/v1/courses/${courseId}/assignments/`, {
    method: 'POST',
    body: payload,
  });
}

export async function updateAssignment(
  id: string,
  changes: Record<string, unknown>,
): Promise<Assignment> {
  return apiMutate<Assignment>(`/api/v1/assignments/${id}/`, { method: 'PATCH', body: changes });
}

export async function setAssignmentStatus(
  id: string,
  status: AcademicLifecycle,
): Promise<Assignment> {
  return apiMutate<Assignment>(`/api/v1/assignments/${id}/status/`, {
    method: 'POST',
    body: { status },
  });
}

export async function listSubmissions(
  assignmentId: string,
  query: { status?: string; page?: number } = {},
): Promise<Paginated<StaffSubmission>> {
  return apiFetch<Paginated<StaffSubmission>>(
    `/api/v1/assignments/${assignmentId}/submissions/${queryString(query)}`,
  );
}

export async function listMySubmissions(): Promise<Paginated<Submission>> {
  return apiFetch<Paginated<Submission>>('/api/v1/submissions/mine/');
}

/** Hand in one attempt. Files travel as repeated `files` parts. */
export async function submitAssignment(
  assignmentId: string,
  payload: { files?: File[]; text_answer?: string; link_url?: string },
): Promise<Submission> {
  const form = new FormData();
  for (const file of payload.files ?? []) form.append('files', file);
  if (payload.text_answer) form.append('text_answer', payload.text_answer);
  if (payload.link_url) form.append('link_url', payload.link_url);
  return apiMutate<Submission>(`/api/v1/assignments/${assignmentId}/submit/`, {
    method: 'POST',
    formData: form,
  });
}

export async function gradeSubmission(
  submissionId: string,
  marks: string,
  feedback = '',
): Promise<StaffSubmission> {
  return apiMutate<StaffSubmission>(`/api/v1/submissions/${submissionId}/grade/`, {
    method: 'POST',
    body: { marks, feedback },
  });
}

export async function returnSubmission(
  submissionId: string,
  feedback: string,
): Promise<StaffSubmission> {
  return apiMutate<StaffSubmission>(`/api/v1/submissions/${submissionId}/return/`, {
    method: 'POST',
    body: { feedback },
  });
}

/**
 * The URL a submitted file is served from.
 *
 * A plain link rather than a fetch: the backend answers with an attachment
 * disposition and an opaque content type, so the browser saves it instead of
 * rendering it. Authorization is re-checked on that request.
 */
export function submissionFileUrl(fileId: string): string {
  return `${apiBaseUrl()}/api/v1/submissions/files/${fileId}/download/`;
}
