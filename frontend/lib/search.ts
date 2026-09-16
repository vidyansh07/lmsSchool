/**
 * Global search (`/api/v1/search/`, ERP Phase 11) — the command palette's
 * one data source beyond its own local navigation list.
 *
 * `q` must be at least 2 characters server-side (`API_CONTRACTS.md`); this
 * client does not re-validate that itself; the command palette is the one
 * caller and it already debounces and gates on the same minimum, per
 * DESIGN_DECISIONS.md's "no mouse-hover fetches" (a fetch fires only once
 * a person has typed enough to mean it).
 */

import { apiFetch, queryString } from "./api";
import type { SearchResponse } from "@/types/api";

export interface SearchQuery {
  q: string;
  /** Widen one type past its default cap of 5 results. */
  types?: string[];
}

export async function search({ q, types }: SearchQuery): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(
    `/api/v1/search/${queryString({
      q,
      types: types && types.length > 0 ? types.join(",") : undefined,
    })}`,
  );
}
