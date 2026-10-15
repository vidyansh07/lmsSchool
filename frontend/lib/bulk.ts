/**
 * Acting on many rows at once (`apps/common/bulk.py`).
 *
 * Every bulk endpoint takes the same target — the ticked ids, or "every row
 * these filters match" — and answers in the same shape: how many were done,
 * and which were skipped and why. A list screen builds the target with
 * `bulkTarget` from its selection and its query, so "select all matching"
 * sends the filters the screen is showing rather than a page of ids.
 */

import { apiMutate } from './api';
import type { UseBulkSelectionResult } from '@/hooks/use-bulk-selection';

export type BulkTarget = { ids: string[] } | { filters: Record<string, string> };

export interface BulkSkip {
  id: string;
  label: string;
  reason: string;
}

export interface BulkResult {
  action: string;
  total: number;
  done: number;
  skipped: BulkSkip[];
}

/** The target for a selection: ticked ids, or the screen's own filters. */
export function bulkTarget(
  selection: Pick<UseBulkSelectionResult<string>, 'selectAllMatching' | 'selectedIds'>,
  query: Record<string, string | number | undefined>,
  filterKeys: readonly string[],
): BulkTarget {
  if (!selection.selectAllMatching) return { ids: [...selection.selectedIds] };
  const filters: Record<string, string> = {};
  for (const key of ['search', ...filterKeys]) {
    const value = query[key];
    if (value !== undefined && value !== null && String(value) !== '') filters[key] = String(value);
  }
  return { filters };
}

/** A stable key for "the filters changed", so a selection never carries over. */
export function selectionKey(
  query: Record<string, string | number | undefined>,
  filterKeys: readonly string[],
): string {
  return JSON.stringify(['search', ...filterKeys].map((key) => query[key] ?? ''));
}

export async function bulkUsers(
  body: BulkTarget &
    (
      | { action: 'resend_invitation' }
      | { action: 'move_centre'; branch_id: string; reason: string }
    ),
): Promise<BulkResult> {
  return apiMutate<BulkResult>('/api/v1/users/bulk/', { method: 'POST', body });
}

export async function bulkAssignEnquiryOwner(
  body: BulkTarget & { owner_id: string | null },
): Promise<BulkResult> {
  return apiMutate<BulkResult>('/api/v1/enquiries/bulk/', {
    method: 'POST',
    body: { action: 'assign_owner', ...body },
  });
}

export async function bulkTransferEnrollments(
  body: BulkTarget & { batch_id: string; reason: string; is_upgrade?: boolean },
): Promise<BulkResult> {
  return apiMutate<BulkResult>('/api/v1/enrollments/bulk-transfer/', { method: 'POST', body });
}
