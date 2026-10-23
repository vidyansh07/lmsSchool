/**
 * Admissions (`/api/v1/admissions/`) — one student signing up for one or more
 * courses on one date.
 *
 * The admission groups; the money stays per course. Each course line still
 * creates its own enrolment and its own fee plan, so "which course was that
 * ₹5,000 for" keeps the answer it has always had. What the admission adds is
 * the one agreed total and the one discount, which the server *splits* across
 * those plans rather than holding centrally.
 */

import { apiFetch, apiMutate, queryString } from './api';
import type { Paginated } from '@/types/api';

export type AdmissionLineKind = 'course' | 'additional_fee';
export type AdmissionStatus = 'active' | 'cancelled';
export type DiscountKind = 'flat' | 'percent';

export interface AdmissionLine {
  id: string;
  kind: AdmissionLineKind;
  course_id: string | null;
  course_title: string | null;
  label: string;
  /** The course title, or the additional fee's own name. */
  name: string;
  charged_on_id: string | null;
  quantity: number;
  unit_fee: string;
  line_total: string;
  /** This line's share of the admission's discount, in rupees. */
  discount_share: string;
  enrollment_id: string | null;
}

/** Total / Paid / Uncleared / Refund / Balance, read from the fee ledger.
 *  `uncleared` is part of `paid`, not beside it: a cheque handed over has
 *  been paid and the balance has dropped; what is uncertain is whether the
 *  bank will honour it. */
export interface AdmissionMoney {
  total: string;
  paid: string;
  uncleared: string;
  refund: string;
  balance: string;
}

export interface Admission {
  id: string;
  student_id: string;
  student_name: string;
  branch_id: string;
  branch_name: string | null;
  academic_year_id: string | null;
  academic_year: string | null;
  admission_date: string;
  status: AdmissionStatus;
  is_cancelled: boolean;
  discount_kind: DiscountKind;
  discount_amount: string;
  discount_percent: string | null;
  /** What the lines come to before the discount. */
  gross_total: string;
  /** What was agreed: the lines less the discount. */
  total_fees: string;
  note: string;
  money: AdmissionMoney;
  lines: AdmissionLine[];
  created_by: string | null;
  cancelled_at: string | null;
  cancellation_reason: string;
  created_at: string;
  updated_at: string;
}

export interface AdmissionLineInput {
  kind: AdmissionLineKind;
  course?: string;
  label?: string;
  quantity?: number;
  unit_fee: string;
  /** For an additional fee: the *index* of the course line it is charged on,
   *  a position in this same list. The lines have no ids yet. */
  charged_on?: number;
}

export function listAdmissions(
  query: { student?: string; status?: AdmissionStatus | ''; academic_year?: string } = {},
): Promise<Paginated<Admission>> {
  return apiFetch<Paginated<Admission>>(`/api/v1/admissions/${queryString(query)}`);
}

export function getAdmission(id: string): Promise<Admission> {
  return apiFetch<Admission>(`/api/v1/admissions/${id}/`);
}

export function createAdmission(input: {
  student: string;
  academic_year?: string | null;
  admission_date?: string;
  discount_kind?: DiscountKind;
  discount_value?: string;
  note?: string;
  lines: AdmissionLineInput[];
}): Promise<Admission> {
  return apiMutate<Admission>('/api/v1/admissions/', { method: 'POST', body: input });
}

/** Ends it, settling each course's money through the fee ledger. */
export function cancelAdmission(id: string, reason: string): Promise<Admission> {
  return apiMutate<Admission>(`/api/v1/admissions/${id}/cancel/`, {
    method: 'POST',
    body: { reason },
  });
}
