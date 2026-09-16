/**
 * Saved filters (`/api/v1/saved-filters/?screen=`, ERP Phase 11, DATA_MODEL.md
 * `SavedFilter`) — a person's own named filter presets for one screen, moved
 * to the server per DESIGN_DECISIONS.md ("Search and saved filters": "Saved
 * filters move to the server (per user, per screen) and appear as chips
 * above lists; localStorage remains a cache."). This is distinct from
 * `hooks/use-saved-filters.ts`, which is that localStorage cache.
 *
 * A bare array, not a `Paginated<T>` envelope: `saved-filters` is small and
 * scoped to one user and one screen, the same shape this codebase already
 * uses for other small per-caller lists (`listRoles`, `getUserAudit`).
 */

import { apiFetch, apiMutate, queryString } from "./api";
import type { SavedFilter } from "@/types/api";

export async function listSavedFilters(screen: string): Promise<SavedFilter[]> {
  return apiFetch<SavedFilter[]>(`/api/v1/saved-filters/${queryString({ screen })}`);
}

export interface CreateSavedFilterPayload {
  screen: string;
  name: string;
  filters: Record<string, unknown>;
}

export async function createSavedFilter(payload: CreateSavedFilterPayload): Promise<SavedFilter> {
  return apiMutate<SavedFilter>("/api/v1/saved-filters/", {
    method: "POST",
    body: payload,
  });
}

export async function deleteSavedFilter(id: string): Promise<void> {
  await apiMutate<void>(`/api/v1/saved-filters/${id}/`, { method: "DELETE" });
}
