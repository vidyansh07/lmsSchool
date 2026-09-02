/** API calls for projects (Phase 5.1–5.3). */

import { apiBaseUrl } from './env';
import { apiFetch, apiMutate, queryString } from './api';
import type {
  AcademicLifecycle,
  Paginated,
  Project,
  ProjectWorkStatus,
  RequiredProjectProgress,
  ReviewerProjectWork,
  StudentProject,
  StudentProjectWork,
} from '@/types/api';

export interface ProjectQuery {
  course?: string;
  batch?: string;
  status?: string;
  kind?: string;
  is_required?: string;
  page?: number;
  ordering?: string;
  [key: string]: string | number | undefined;
}

export async function listProjects(query: ProjectQuery = {}): Promise<Paginated<Project>> {
  return apiFetch<Paginated<Project>>(`/api/v1/projects/${queryString(query)}`);
}

export async function listMyProjects(
  query: ProjectQuery = {},
): Promise<Paginated<StudentProject>> {
  return apiFetch<Paginated<StudentProject>>(`/api/v1/projects/mine/${queryString(query)}`);
}

export async function getProject(id: string): Promise<Project> {
  return apiFetch<Project>(`/api/v1/projects/${id}/`);
}

export async function createProject(
  courseId: string,
  payload: Record<string, unknown>,
): Promise<Project> {
  return apiMutate<Project>(`/api/v1/courses/${courseId}/projects/`, {
    method: 'POST',
    body: payload,
  });
}

export async function setProjectStatus(
  id: string,
  status: AcademicLifecycle,
): Promise<Project> {
  return apiMutate<Project>(`/api/v1/projects/${id}/status/`, {
    method: 'POST',
    body: { status },
  });
}

export async function assignProject(
  id: string,
): Promise<{ assigned: number; already_had: number }> {
  return apiMutate(`/api/v1/projects/${id}/assign/`, { method: 'POST' });
}

export async function listProjectWork(
  projectId: string,
): Promise<Paginated<ReviewerProjectWork>> {
  return apiFetch<Paginated<ReviewerProjectWork>>(`/api/v1/projects/${projectId}/submissions/`);
}

export async function getMyProjectWork(projectId: string): Promise<StudentProjectWork> {
  return apiFetch<StudentProjectWork>(`/api/v1/projects/${projectId}/work/`);
}

function workForm(payload: {
  files?: File[];
  repository_url?: string;
  deployment_url?: string;
  notes?: string;
}): FormData {
  const form = new FormData();
  for (const file of payload.files ?? []) form.append('files', file);
  if (payload.repository_url !== undefined) form.append('repository_url', payload.repository_url);
  if (payload.deployment_url !== undefined) form.append('deployment_url', payload.deployment_url);
  if (payload.notes !== undefined) form.append('notes', payload.notes);
  return form;
}

/** A working save. Does not hand anything in. */
export async function saveProjectWork(
  projectId: string,
  payload: { files?: File[]; repository_url?: string; deployment_url?: string; notes?: string },
): Promise<StudentProjectWork> {
  return apiMutate<StudentProjectWork>(`/api/v1/projects/${projectId}/work/`, {
    method: 'PATCH',
    formData: workForm(payload),
  });
}

export async function submitProjectWork(
  projectId: string,
  payload: { files?: File[]; repository_url?: string; deployment_url?: string; notes?: string },
): Promise<StudentProjectWork> {
  return apiMutate<StudentProjectWork>(`/api/v1/projects/${projectId}/work/`, {
    method: 'POST',
    formData: workForm(payload),
  });
}

export async function reviewProject(
  workId: string,
  payload: {
    outcome: ProjectWorkStatus;
    feedback?: string;
    marks?: string;
    rubric_scores?: Record<string, string>;
  },
): Promise<ReviewerProjectWork> {
  return apiMutate<ReviewerProjectWork>(`/api/v1/projects/submissions/${workId}/review/`, {
    method: 'POST',
    body: payload,
  });
}

export async function listRequiredProjectProgress(): Promise<RequiredProjectProgress[]> {
  return apiFetch<RequiredProjectProgress[]>('/api/v1/projects/mine/required/');
}

/** Served as an opaque attachment; authorization is re-checked on the request. */
export function projectFileUrl(fileId: string): string {
  return `${apiBaseUrl()}/api/v1/projects/files/${fileId}/`;
}
