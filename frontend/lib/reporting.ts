/** API calls for reports, analytics, dashboards and data tools (Phase 8). */

import { apiBaseUrl } from './env';
import { apiFetch, apiMutate, queryString } from './api';
import type {
  AcademicEvent,
  AdminDashboard,
  BatchSummary,
  BulkImport,
  LmsMetric,
  ReportDefinition,
  ReportPage,
  TrainerWorkload,
  TrendPoint,
} from '@/types/api';

export interface ReportFilters {
  batch?: string;
  course?: string;
  [key: string]: string | number | undefined;
}

// --- Reports ---------------------------------------------------------------

export async function listReports(): Promise<ReportDefinition[]> {
  return apiFetch<ReportDefinition[]>('/api/v1/reports/');
}

export async function runReport(key: string, filters: ReportFilters = {}): Promise<ReportPage> {
  return apiFetch<ReportPage>(`/api/v1/reports/${key}/${queryString(filters)}`);
}

/**
 * A plain link, not a fetch: the backend streams the CSV as an attachment and
 * re-checks the export capability on that request.
 */
export function reportExportUrl(key: string, filters: ReportFilters = {}): string {
  return `${apiBaseUrl()}/api/v1/reports/${key}/export/${queryString(filters)}`;
}

// --- Analytics -------------------------------------------------------------

export async function listMetrics(filters: ReportFilters = {}): Promise<LmsMetric[]> {
  return apiFetch<LmsMetric[]>(`/api/v1/reports/metrics/${queryString(filters)}`);
}

export async function attendanceTrend(
  filters: ReportFilters & { weeks?: number } = {},
): Promise<TrendPoint[]> {
  return apiFetch<TrendPoint[]>(
    `/api/v1/reports/metrics/attendance-trend/${queryString(filters)}`,
  );
}

// --- Dashboards ------------------------------------------------------------

export async function adminDashboard(): Promise<AdminDashboard> {
  return apiFetch<AdminDashboard>('/api/v1/dashboards/admin/');
}

export async function trainerWorkload(): Promise<TrainerWorkload> {
  return apiFetch<TrainerWorkload>('/api/v1/dashboards/workload/');
}

export async function batchSummaries(): Promise<BatchSummary[]> {
  return apiFetch<BatchSummary[]>('/api/v1/dashboards/batches/');
}

// --- Bulk import: preview, then confirm ------------------------------------

export async function previewStudentImport(file: File, batchId?: string): Promise<BulkImport> {
  const form = new FormData();
  form.append('file', file);
  if (batchId) form.append('batch', batchId);
  return apiMutate<BulkImport>('/api/v1/imports/students/', {
    method: 'POST',
    formData: form,
  });
}

export async function previewAttendanceImport(
  sessionId: string,
  file: File,
): Promise<BulkImport> {
  const form = new FormData();
  form.append('file', file);
  return apiMutate<BulkImport>(`/api/v1/imports/sessions/${sessionId}/attendance/`, {
    method: 'POST',
    formData: form,
  });
}

export async function confirmImport(importId: string): Promise<BulkImport> {
  return apiMutate<BulkImport>(`/api/v1/imports/${importId}/confirm/`, { method: 'POST' });
}

export async function rejectImport(importId: string): Promise<BulkImport> {
  return apiMutate<BulkImport>(`/api/v1/imports/${importId}/reject/`, { method: 'POST' });
}

// --- Academic calendar -----------------------------------------------------

export async function listAcademicEvents(year?: number): Promise<AcademicEvent[]> {
  return apiFetch<AcademicEvent[]>(`/api/v1/academics/calendar/${queryString({ year })}`);
}

export async function addAcademicEvent(payload: {
  name: string;
  kind: string;
  start_date: string;
  end_date: string;
  note?: string;
}): Promise<AcademicEvent> {
  return apiMutate<AcademicEvent>('/api/v1/academics/calendar/', {
    method: 'POST',
    body: payload,
  });
}

export async function removeAcademicEvent(id: string): Promise<void> {
  await apiMutate<void>(`/api/v1/academics/calendar/${id}/`, { method: 'DELETE' });
}
