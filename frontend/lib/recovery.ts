/**
 * The recycle bin — reading and acting on what `apps.common.recovery` exposes.
 *
 * The backend deliberately keeps this generic: any model that inherits
 * `SoftDeleteModel` shows up here automatically, addressed by its
 * app-qualified label (`"dsr.dsr"`, `"batches.batch"`, …) rather than by a
 * frontend-maintained list of "the kinds of thing that can be deleted". That
 * is why every function below takes `label` as a plain string it received
 * from the API a moment earlier, rather than a closed union this file would
 * have to keep in sync with the backend's model registry by hand.
 *
 * Three verbs, matching `apps.common.deletion` exactly, because conflating
 * any two of them would be the same mistake at the UI layer that module's
 * docstring warns against at the service layer:
 *  - `listDeletedRecords` / `restoreRecord` — routine, reversible, available
 *    to anyone holding `record.view_deleted` / `record.restore`.
 *  - `purgeRecord` — destruction with no undo, gated separately by
 *    `record.purge`, which only a superadmin holds. The reason is required by
 *    the serializer (`PurgeSerializer.reason` disallows blank), so this
 *    throws the same `ApiError` a blank submission would produce rather than
 *    validating client-side and inventing a second source of truth for the
 *    rule — the caller still surfaces it as a normal field error via
 *    `fieldErrors`.
 */

import { apiFetch, apiMutate, queryString } from './api';
import type { ListQuery } from './people';
import type { Paginated } from '@/types/api';

/** One entry of `GET /api/v1/recovery/` — a kind of record, and how many are in the bin. */
export interface BinSummary {
  label: string;
  verbose_name: string;
  deleted_count: number;
}

/**
 * One deleted row, matching `DeletedRecordSerializer` field for field.
 *
 * Every field the serializer promises is always present — including
 * `deleted_by`, which is `null` specifically when the account that deleted
 * the record has itself since been removed. That is a fact worth rendering
 * ("Unknown"), never a blank cell or a key this type would let a caller skip.
 */
export interface DeletedRecord {
  id: string;
  label: string;
  describes: string;
  deleted_at: string;
  deleted_by: string | null;
  delete_reason: string;
}

/** Every kind currently holding at least one deleted record. An empty kind is
 *  omitted by the backend itself — see `RecycleBinView.get` — so there is no
 *  zero-count row for this file to filter out a second time. */
export function listRecoveryKinds(): Promise<BinSummary[]> {
  return apiFetch<BinSummary[]>('/api/v1/recovery/');
}

/** One kind's deleted records, most recently removed first. */
export function listDeletedRecords(label: string, query: ListQuery = {}): Promise<Paginated<DeletedRecord>> {
  return apiFetch<Paginated<DeletedRecord>>(`/api/v1/recovery/${label}/${queryString(query)}`);
}

/** Bring one record back. Ordinary and reversible — no reason required. */
export function restoreRecord(label: string, id: string): Promise<DeletedRecord> {
  return apiMutate<DeletedRecord>(`/api/v1/recovery/${label}/${id}/restore/`, { method: 'POST' });
}

/**
 * Destroy one record permanently. There is no undo, on this screen or on the
 * server — see `apps.common.deletion.purge`. `reason` is sent exactly as
 * typed; the caller is responsible for rejecting a blank one before this is
 * called, so that failure reads as an inline form problem rather than a
 * round trip to discover it.
 */
export function purgeRecord(label: string, id: string, reason: string): Promise<void> {
  return apiMutate<void>(`/api/v1/recovery/${label}/${id}/purge/`, { method: 'POST', body: { reason } });
}
