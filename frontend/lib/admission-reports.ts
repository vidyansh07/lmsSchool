/**
 * The five admissions reports (`/api/v1/admissions/reports/{tab}/`).
 *
 * Every figure comes from the server, which reads them from the records
 * themselves. Nothing is summed in the browser: the tile the owner reads out
 * loud has to be the same number as the rows underneath it, and a screen that
 * does its own arithmetic is how the two come to differ.
 */

import { apiFetch, queryString } from './api';

export type ReportTab =
  | 'overall'
  | 'discount'
  | 'expiry'
  | 'additional-fees'
  | 'coursewise';

export const REPORT_TABS: { key: ReportTab; label: string }[] = [
  { key: 'overall', label: 'Overall admissions' },
  { key: 'discount', label: 'Discount' },
  { key: 'expiry', label: 'Admission Expiry' },
  { key: 'additional-fees', label: 'Additional Fees' },
  { key: 'coursewise', label: 'Coursewise Admission' },
];

export interface ReportFilters {
  /** Every filter is an optional string, and the index signature is what lets
   *  the whole object go to `queryString` without being copied key by key. */
  [key: string]: string | undefined;
  academic_year?: string;
  status?: string;
  course?: string;
  batch?: string;
  user?: string;
  school?: string;
  start_date?: string;
  end_date?: string;
}

/** Tiles and rows both vary per tab — the shapes are fixed on the server and
 *  asserted in its own tests, so this stays honest about being loose rather
 *  than claiming five precise shapes it cannot enforce. */
export interface AdmissionReport {
  tiles: Record<string, string | number>;
  rows: Record<string, string | number | null>[];
}

export function getAdmissionReport(
  tab: ReportTab,
  filters: ReportFilters = {},
): Promise<AdmissionReport> {
  return apiFetch<AdmissionReport>(
    `/api/v1/admissions/reports/${tab}/${queryString(filters)}`,
  );
}
