/**
 * Enquiries (`/api/v1/enquiries/`) — the Meritto-style lead pipeline.
 *
 * An enquiry is created by submitting the enquiry form (`fillForm("enquiry",
 * …)` in `lib/forms.ts`), never directly, so every lead arrives the same way
 * and starts the same automation rules. This client reads enquiries and
 * changes their stage, owner and follow-up.
 */

import { apiFetch, apiMutate } from "./api";
import type { EnquiryDetail, EnquiryStage, EnquirySummary, LeadChannel } from "@/types/api";

export interface EnquiryChanges {
  stage?: EnquiryStage;
  source?: string;
  /** Follows the source unless set by hand. */
  channel?: LeadChannel;
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

/** Record that the lead was registered as this student (the wizard's last
 *  step when it was opened from an enquiry). */
export async function registerEnquiry(id: string, studentId: string): Promise<EnquiryDetail> {
  return apiMutate<EnquiryDetail>(`/api/v1/enquiries/${id}/register/`, {
    method: "POST",
    body: { student: studentId },
  });
}

/** Where "Register this lead" goes: the wizard, filled in from the lead. */
export function registerLeadHref(id: string): string {
  return `/admissions/new?enquiry=${encodeURIComponent(id)}`;
}

/** The list path for `useApi`, with the filters the pipeline screen uses. */
export type EnquiryFollowUpFilter = "" | "overdue" | "today" | "none";

export function enquiryListPath(filters: {
  stage?: EnquiryStage | "";
  channel?: LeadChannel | "";
  source?: string;
  follow_up?: EnquiryFollowUpFilter;
  created_after?: string;
  created_before?: string;
  owner?: string;
  q?: string;
  /** `meritto`: leads Meritto sent. `lms`: entered here. */
  managed_by?: "" | "meritto" | "lms";
  /** Meritto leads not yet registered. */
  ready_to_admit?: boolean;
  page?: number;
}): string {
  const query = new URLSearchParams();
  if (filters.stage) query.set("stage", filters.stage);
  if (filters.channel) query.set("channel", filters.channel);
  if (filters.source) query.set("source", filters.source);
  if (filters.follow_up) query.set("follow_up", filters.follow_up);
  if (filters.created_after) query.set("created_after", filters.created_after);
  if (filters.created_before) query.set("created_before", filters.created_before);
  if (filters.owner) query.set("owner", filters.owner);
  if (filters.q) query.set("q", filters.q);
  if (filters.managed_by) query.set("managed_by", filters.managed_by);
  if (filters.ready_to_admit) query.set("ready_to_admit", "true");
  if (filters.page && filters.page > 1) query.set("page", String(filters.page));
  const suffix = query.toString();
  return `/api/v1/enquiries/${suffix ? `?${suffix}` : ""}`;
}
