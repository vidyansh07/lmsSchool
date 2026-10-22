/**
 * Placements (`/api/v1/placements/`) — where a student ended up, and the
 * offers on the way there.
 *
 * One row per offer, not per student: an officer's record of four interviews,
 * three declined and one joined, is four rows. Reading needs
 * `placement.view_any` for the centre's offers, and a student reads their own
 * without it; writing needs `placement.manage`. Both are re-checked by the
 * server on every request — these functions hide no decision of their own.
 */

import { apiFetch, apiMutate, queryString } from './api';
import type { Paginated, Placement, PlacementStatus, PlacementSummary } from '@/types/api';

export interface PlacementQuery {
  status?: PlacementStatus | '';
  /** Only offers that became a job (accepted or joined), or only those that
   *  did not. A single status cannot express it. */
  placed?: boolean;
  student?: string;
  company?: string;
  offered_after?: string;
  offered_before?: string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export function listPlacements(query: PlacementQuery = {}): Promise<Paginated<Placement>> {
  const { placed, ...rest } = query;
  // `placed` is spelled out rather than coerced by `String(false) === 'false'`
  // luck: `queryString` drops empty strings, and an unset boolean must drop
  // out of the query entirely rather than arrive as "undefined".
  const params = { ...rest, placed: placed === undefined ? undefined : String(placed) };
  return apiFetch<Paginated<Placement>>(`/api/v1/placements/${queryString(params)}`);
}

export function placementSummary(): Promise<PlacementSummary> {
  return apiFetch<PlacementSummary>('/api/v1/placements/summary/');
}

export interface PlacementInput {
  student: string;
  company: string;
  role_title: string;
  offered_on: string;
  status?: PlacementStatus;
  annual_package?: string | null;
  location?: string;
  joined_on?: string | null;
  notes?: string;
  enrollment?: string | null;
}

/** Records one offer. The centre is not a field: the server takes it from the
 *  student, so nothing can be filed into a centre the caller cannot read. */
export function recordPlacement(input: PlacementInput): Promise<Placement> {
  return apiMutate<Placement>('/api/v1/placements/', { method: 'POST', body: input });
}

/** Changes one. `student` is absent on purpose — an offer recorded against
 *  the wrong person is withdrawn and recorded again, so the first student's
 *  record keeps its history. */
export function updatePlacement(
  id: string,
  changes: Partial<Omit<PlacementInput, 'student'>>,
): Promise<Placement> {
  return apiMutate<Placement>(`/api/v1/placements/${id}/`, { method: 'PATCH', body: changes });
}
