/** API calls for progress, completion and certificates (Phase 6). */

import { apiBaseUrl } from './env';
import { apiFetch, apiMutate, queryString } from './api';
import type {
  Certificate,
  CertificateTemplate,
  CompletionEvaluation,
  CourseCompletion,
  Paginated,
  ProgressReport,
  PublicCertificate,
} from '@/types/api';

// --- Progress --------------------------------------------------------------

/**
 * A student's own progress and completion standing.
 *
 * The single source (§6.3): no screen recomputes any of this from parts it
 * happens to have.
 */
export async function listMyProgress(): Promise<CompletionEvaluation[]> {
  return apiFetch<CompletionEvaluation[]>('/api/v1/progress/mine/');
}

export async function getEnrollmentProgress(
  enrollmentId: string,
): Promise<CompletionEvaluation> {
  return apiFetch<CompletionEvaluation>(`/api/v1/progress/enrollments/${enrollmentId}/`);
}

export async function getProgressReport(enrollmentId: string): Promise<ProgressReport> {
  return apiFetch<ProgressReport>(`/api/v1/progress/enrollments/${enrollmentId}/report/`);
}

// --- Completion ------------------------------------------------------------

export interface CompletionQuery {
  status?: string;
  batch?: string;
  course?: string;
  page?: number;
  ordering?: string;
  [key: string]: string | number | undefined;
}

export async function listCompletions(
  query: CompletionQuery = {},
): Promise<Paginated<CourseCompletion>> {
  return apiFetch<Paginated<CourseCompletion>>(`/api/v1/completions/${queryString(query)}`);
}

export async function refreshBatchCompletions(batchId: string): Promise<CourseCompletion[]> {
  return apiMutate<CourseCompletion[]>(`/api/v1/batches/${batchId}/completions/refresh/`, {
    method: 'POST',
  });
}

export async function approveCompletion(
  enrollmentId: string,
  payload: { completed_on?: string; note?: string; override?: boolean } = {},
): Promise<CourseCompletion> {
  return apiMutate<CourseCompletion>(
    `/api/v1/completions/enrollments/${enrollmentId}/approve/`,
    { method: 'POST', body: payload },
  );
}

export async function rejectCompletion(
  enrollmentId: string,
  note: string,
): Promise<CourseCompletion> {
  return apiMutate<CourseCompletion>(`/api/v1/completions/enrollments/${enrollmentId}/reject/`, {
    method: 'POST',
    body: { note },
  });
}

export async function reopenCompletion(
  enrollmentId: string,
  note: string,
): Promise<CourseCompletion> {
  return apiMutate<CourseCompletion>(`/api/v1/completions/enrollments/${enrollmentId}/reopen/`, {
    method: 'POST',
    body: { note },
  });
}

// --- Certificates ----------------------------------------------------------

export async function listCertificates(
  query: { status?: string; search?: string; page?: number } = {},
): Promise<Paginated<Certificate>> {
  return apiFetch<Paginated<Certificate>>(`/api/v1/certificates/${queryString(query)}`);
}

export async function listMyCertificates(): Promise<Certificate[]> {
  return apiFetch<Certificate[]>('/api/v1/certificates/mine/');
}

export async function listCertificateTemplates(): Promise<CertificateTemplate[]> {
  return apiFetch<CertificateTemplate[]>('/api/v1/certificates/templates/');
}

export async function createCertificateTemplate(
  payload: Record<string, unknown>,
): Promise<CertificateTemplate> {
  return apiMutate<CertificateTemplate>('/api/v1/certificates/templates/', {
    method: 'POST',
    body: payload,
  });
}

export async function issueCertificate(
  enrollmentId: string,
  templateId?: string,
): Promise<Certificate> {
  return apiMutate<Certificate>(`/api/v1/certificates/enrollments/${enrollmentId}/issue/`, {
    method: 'POST',
    body: templateId ? { template: templateId } : {},
  });
}

export async function reissueCertificate(
  certificateId: string,
  reason: string,
): Promise<Certificate> {
  return apiMutate<Certificate>(`/api/v1/certificates/${certificateId}/reissue/`, {
    method: 'POST',
    body: { reason },
  });
}

export async function revokeCertificate(
  certificateId: string,
  reason: string,
): Promise<Certificate> {
  return apiMutate<Certificate>(`/api/v1/certificates/${certificateId}/revoke/`, {
    method: 'POST',
    body: { reason },
  });
}

/** The PDF is drawn on demand, so this is a plain link rather than a fetch. */
export function certificatePdfUrl(certificateId: string): string {
  return `${apiBaseUrl()}/api/v1/certificates/${certificateId}/pdf/`;
}

/** §6.8 — anonymous by design. No credentials travel with this call. */
export async function verifyCertificate(code: string): Promise<PublicCertificate> {
  return apiFetch<PublicCertificate>(`/api/v1/verify/${encodeURIComponent(code)}/`);
}
