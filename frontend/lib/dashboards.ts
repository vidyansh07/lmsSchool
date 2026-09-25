/**
 * Cross-role dashboard summaries that do not already have a natural home in
 * another `lib/*.ts` module (`lib/reporting.ts` owns the admin one,
 * `lib/manage.ts` the manager one — both predate this file). New dashboards
 * land here rather than growing a third pattern.
 */

import { apiFetch } from './api';
import type { CounsellorDashboard, CounsellorPipeline } from '@/types/api';

/** `GET /api/v1/dashboards/counsellor/` — `student.create`, §6 of
 *  `docs/erp/USER_JOURNEYS.md` ("Dashboards — loading contract"). */
export async function getCounsellorDashboard(): Promise<CounsellorDashboard> {
  return apiFetch<CounsellorDashboard>('/api/v1/dashboards/counsellor/');
}

export async function getCounsellorPipeline(
  params: { weeks?: number } = {},
): Promise<CounsellorPipeline> {
  const query = params.weeks ? `?weeks=${params.weeks}` : '';
  return apiFetch<CounsellorPipeline>(`/api/v1/dashboards/counsellor/pipeline/${query}`);
}
