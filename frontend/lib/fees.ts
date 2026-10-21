/**
 * API calls for the fee ledger (`/api/v1/fees/`).
 *
 * A fee belongs to an enrolment, not a student: a student on two courses has
 * two fees, each agreed and paid down on its own. Every write here is a
 * counsellor's or manager's action and is audited server-side; nothing is
 * ever deleted — a payment recorded in error is *voided*, with a reason.
 */

import { apiFetch, apiMutate } from './api';
import type {
  FeeEmail,
  FeeEmailQueued,
  FeeHistoryEntry,
  FeePayment,
  FeePlan,
  FeeCollectionsTrendPoint,
  FeesOverview,
  InstallmentInput,
  PaymentMethod,
  StudentFeeSummary,
} from '@/types/api';

const BASE = '/api/v1/fees';

/** The fee for one enrolment. Rejects with a 404 `ApiError` when none is set yet. */
export async function getEnrollmentFee(enrollmentId: string): Promise<FeePlan> {
  return apiFetch<FeePlan>(`${BASE}/enrollments/${enrollmentId}/`);
}

export async function setEnrollmentFee(
  enrollmentId: string,
  payload: {
    agreed_amount: string | number;
    discount_amount?: string | number;
    /** Sent: the discount is this percentage of the fee and the server works
     *  out the rupees. Null or left out: `discount_amount` is a flat discount. */
    discount_percent?: string | number | null;
    discount_reason?: string;
    notes?: string;
    /** Sent: this is the schedule (empty = ad hoc). Left out: the server's default six. */
    installments?: InstallmentInput[];
    installment_count?: number;
  },
): Promise<FeePlan> {
  return apiMutate<FeePlan>(`${BASE}/enrollments/${enrollmentId}/`, {
    method: 'PUT',
    body: payload,
  });
}

/** Replace the instalment schedule. An empty list goes back to ad hoc collection. */
export async function setInstallments(
  enrollmentId: string,
  installments: InstallmentInput[],
): Promise<FeePlan> {
  return apiMutate<FeePlan>(`${BASE}/enrollments/${enrollmentId}/installments/`, {
    method: 'PUT',
    body: { installments },
  });
}

/**
 * The default schedule, exactly as the server would build it: `count` equal
 * slices of `payable`, the odd paisa on the first, due today and then every
 * thirty days. Computed here too so the counsellor sees and can edit the
 * rows before anything is saved.
 */
export function defaultInstallments(
  payable: number,
  count = 6,
  start: Date = new Date(),
  gapDays = 30,
): InstallmentInput[] {
  if (!Number.isFinite(payable) || payable <= 0 || count <= 0) return [];
  const total = Math.round(payable * 100);
  const each = Math.floor(total / count);
  const remainder = total - each * count;
  return Array.from({ length: count }, (_, index) => {
    const due = new Date(start);
    due.setDate(due.getDate() + gapDays * index);
    const paise = index === 0 ? each + remainder : each;
    return { amount: (paise / 100).toFixed(2), due_on: isoDate(due) };
  });
}

/** Sum of a schedule's amounts, in rupees, tolerant of half-typed rows. */
export function installmentsTotal(rows: InstallmentInput[]): number {
  return rows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
}

function isoDate(date: Date): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/** "The next ₹N is expected by <date>." Send both `null` to clear it. */
export async function setNextDue(
  enrollmentId: string,
  payload: { next_due_amount: string | number | null; next_due_on: string | null },
): Promise<FeePlan> {
  return apiMutate<FeePlan>(`${BASE}/enrollments/${enrollmentId}/next-due/`, {
    method: 'POST',
    body: payload,
  });
}

export async function recordPayment(
  enrollmentId: string,
  payload: {
    amount: string | number;
    paid_on?: string;
    method: PaymentMethod;
    reference?: string;
    reference_name?: string;
    note?: string;
  },
): Promise<FeePayment> {
  return apiMutate<FeePayment>(`${BASE}/enrollments/${enrollmentId}/payments/`, {
    method: 'POST',
    body: payload,
  });
}

export async function voidPayment(paymentId: string, reason: string): Promise<FeePayment> {
  return apiMutate<FeePayment>(`${BASE}/payments/${paymentId}/void/`, {
    method: 'POST',
    body: { reason },
  });
}

/** Who changed what, when — newest first. */
export async function getFeeHistory(enrollmentId: string): Promise<FeeHistoryEntry[]> {
  return apiFetch<FeeHistoryEntry[]>(`${BASE}/enrollments/${enrollmentId}/history/`);
}

/** Every fee mail about one enrolment — statements and receipts — newest first. */
export async function listFeeEmails(enrollmentId: string): Promise<FeeEmail[]> {
  return apiFetch<FeeEmail[]>(`${BASE}/enrollments/${enrollmentId}/emails/`);
}

/** Send the fee statement (PDF attached) to the student now. */
export async function emailStatement(enrollmentId: string): Promise<FeeEmailQueued> {
  return apiMutate<FeeEmailQueued>(`${BASE}/enrollments/${enrollmentId}/email-statement/`, {
    method: 'POST',
  });
}

/** Send a payment's receipt (PDF attached) to the student again. */
export async function emailReceipt(paymentId: string): Promise<FeeEmailQueued> {
  return apiMutate<FeeEmailQueued>(`${BASE}/payments/${paymentId}/email-receipt/`, {
    method: 'POST',
  });
}

export async function getStudentFees(studentId: string): Promise<StudentFeeSummary> {
  return apiFetch<StudentFeeSummary>(`${BASE}/students/${studentId}/`);
}

export async function getMyFees(): Promise<StudentFeeSummary> {
  return apiFetch<StudentFeeSummary>(`${BASE}/me/`);
}

export async function getFeesOverview(): Promise<FeesOverview> {
  return apiFetch<FeesOverview>(`${BASE}/overview/`);
}

export async function feeCollectionsTrend(
  params: { weeks?: number } = {},
): Promise<FeeCollectionsTrendPoint[]> {
  const query = params.weeks ? `?weeks=${params.weeks}` : '';
  return apiFetch<FeeCollectionsTrendPoint[]>(`${BASE}/collections-trend/${query}`);
}

/**
 * Give a payment back.
 *
 * A different act from voiding, on a different endpoint. A void says the
 * payment should never have been recorded; a refund says it was correct and
 * the money has gone back. An accountant has to be able to tell them apart.
 */
export async function refundPayment(paymentId: string, reason: string): Promise<FeePayment> {
  return apiMutate<FeePayment>(`/api/v1/fees/payments/${paymentId}/refund/`, {
    method: 'POST',
    body: { reason },
  });
}

/**
 * End an admission and settle its money in one request.
 *
 * One call rather than "cancel the enrolment, then fix the fee": they are one
 * decision, and doing half of it is how the two came to disagree.
 */
export async function cancelAdmission(
  enrollmentId: string,
  body: { cancellation_charge: string; reason: string },
): Promise<FeePlan> {
  return apiMutate<FeePlan>(`/api/v1/fees/enrollments/${enrollmentId}/cancel/`, {
    method: 'POST',
    body,
  });
}
