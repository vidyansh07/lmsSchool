/** API calls for assessments, results and result import (Phase 4.5/4.6). */

import { apiFetch, apiMutate, queryString } from './api';
import type {
  AcademicLifecycle,
  Assessment,
  AssessmentResult,
  MarksSheet,
  Paginated,
  ResultImport,
  StudentAssessment,
} from '@/types/api';

export interface AssessmentQuery {
  batch?: string;
  course?: string;
  category?: string;
  delivery?: string;
  status?: string;
  page?: number;
  ordering?: string;
  [key: string]: string | number | undefined;
}

export async function listAssessments(
  query: AssessmentQuery = {},
): Promise<Paginated<Assessment>> {
  return apiFetch<Paginated<Assessment>>(`/api/v1/assessments/${queryString(query)}`);
}

export async function listMyAssessments(
  query: AssessmentQuery = {},
): Promise<Paginated<StudentAssessment>> {
  return apiFetch<Paginated<StudentAssessment>>(`/api/v1/assessments/mine/${queryString(query)}`);
}

export async function getAssessment(id: string): Promise<Assessment> {
  return apiFetch<Assessment>(`/api/v1/assessments/${id}/`);
}

export async function createAssessment(
  batchId: string,
  payload: Record<string, unknown>,
): Promise<Assessment> {
  return apiMutate<Assessment>(`/api/v1/batches/${batchId}/assessments/`, {
    method: 'POST',
    body: payload,
  });
}

export async function setAssessmentStatus(
  id: string,
  status: AcademicLifecycle,
): Promise<Assessment> {
  return apiMutate<Assessment>(`/api/v1/assessments/${id}/status/`, {
    method: 'POST',
    body: { status },
  });
}

export async function getMarksSheet(assessmentId: string): Promise<MarksSheet> {
  return apiFetch<MarksSheet>(`/api/v1/assessments/${assessmentId}/marks/`);
}

export async function recordResult(
  assessmentId: string,
  payload: {
    enrollment_id: string;
    marks?: string | null;
    is_absent?: boolean;
    remarks?: string;
  },
): Promise<AssessmentResult> {
  return apiMutate<AssessmentResult>(`/api/v1/assessments/${assessmentId}/marks/`, {
    method: 'POST',
    body: payload,
  });
}

export async function listMyResults(): Promise<Paginated<AssessmentResult>> {
  return apiFetch<Paginated<AssessmentResult>>('/api/v1/results/mine/');
}

// --- Import: preview, then confirm ----------------------------------------

/** Step one. Validates the file and reports; writes no results. */
export async function previewImport(assessmentId: string, file: File): Promise<ResultImport> {
  const form = new FormData();
  form.append('file', file);
  return apiMutate<ResultImport>(`/api/v1/assessments/${assessmentId}/imports/`, {
    method: 'POST',
    formData: form,
  });
}

export async function listImports(assessmentId: string): Promise<ResultImport[]> {
  return apiFetch<ResultImport[]>(`/api/v1/assessments/${assessmentId}/imports/`);
}

/** Step two. Applies the previewed rows, all or nothing. */
export async function confirmImport(importId: string): Promise<ResultImport> {
  return apiMutate<ResultImport>(`/api/v1/results/imports/${importId}/confirm/`, {
    method: 'POST',
  });
}

export async function rejectImport(importId: string): Promise<ResultImport> {
  return apiMutate<ResultImport>(`/api/v1/results/imports/${importId}/reject/`, {
    method: 'POST',
  });
}
