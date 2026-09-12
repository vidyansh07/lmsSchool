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
  FeeHistoryEntry,
  FeePayment,
  FeePlan,
  FeesOverview,
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
    discount_reason?: string;
    notes?: string;
  },
): Promise<FeePlan> {
  return apiMutate<FeePlan>(`${BASE}/enrollments/${enrollmentId}/`, {
    method: 'PUT',
    body: payload,
  });
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

export async function getStudentFees(studentId: string): Promise<StudentFeeSummary> {
  return apiFetch<StudentFeeSummary>(`${BASE}/students/${studentId}/`);
}

export async function getMyFees(): Promise<StudentFeeSummary> {
  return apiFetch<StudentFeeSummary>(`${BASE}/me/`);
}

export async function getFeesOverview(): Promise<FeesOverview> {
  return apiFetch<FeesOverview>(`${BASE}/overview/`);
}
