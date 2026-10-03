/**
 * Enquiries (`/api/v1/enquiries/`) — the Meritto-style lead pipeline.
 *
 * An enquiry is created by submitting the enquiry form (`fillForm("enquiry",
 * …)` in `lib/forms.ts`), never directly, so every lead arrives the same way
 * and starts the same automation rules. This client reads enquiries and
 * changes their stage, owner and follow-up.
 */

import { apiFetch, apiMutate } from "./api";
import type { EnquiryDetail, EnquiryStage, EnquirySummary } from "@/types/api";

export interface EnquiryChanges {
  stage?: EnquiryStage;
  owner?: string | null;
  lost_reason?: string;
  lead_quality?: number | null;
  next_follow_up_at?: string | null;
  remarks?: string;
}

export async function getEnquirySummary(): Promise<EnquirySummary> {
  return apiFetch<EnquirySummary>("/api/v1/enquiries/summary/");
}

export async function getEnquiry(id: string): Promise<EnquiryDetail> {
  return apiFetch<EnquiryDetail>(`/api/v1/enquiries/${id}/`);
}

/** Changes an enquiry (its owner, or `enquiry.manage` at its centre). A
 *  changed stage starts any "Enquiry stage changed" rule. */
export async function updateEnquiry(id: string, changes: EnquiryChanges): Promise<EnquiryDetail> {
  return apiMutate<EnquiryDetail>(`/api/v1/enquiries/${id}/`, { method: "PATCH", body: changes });
}

/** The list path for `useApi`, with the filters the pipeline screen uses. */
export function enquiryListPath(filters: {
  stage?: EnquiryStage | "";
  owner?: string;
  q?: string;
  page?: number;
}): string {
  const query = new URLSearchParams();
  if (filters.stage) query.set("stage", filters.stage);
  if (filters.owner) query.set("owner", filters.owner);
  if (filters.q) query.set("q", filters.q);
  if (filters.page && filters.page > 1) query.set("page", String(filters.page));
  const suffix = query.toString();
  return `/api/v1/enquiries/${suffix ? `?${suffix}` : ""}`;
}
