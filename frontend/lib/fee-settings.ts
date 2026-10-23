/**
 * The reference lists the payment dialog picks from: banks, payment
 * categories, tax groups.
 *
 * All three are an administrator's lists rather than enums, because every
 * institute's are different and none of them is a code change. Each has at
 * most one default, which is what the dialog opens with.
 */

import { apiFetch } from './api';

export interface NamedRow {
  id: string;
  name: string;
  is_default?: boolean;
  is_active?: boolean;
}

/** Banks a cheque, draft or deposit went through. Needs `fee.view_any`. */
export function listBanks(): Promise<NamedRow[]> {
  return apiFetch<NamedRow[]>('/api/v1/banks/');
}

export function listPaymentCategories(): Promise<NamedRow[]> {
  return apiFetch<NamedRow[]>('/api/v1/fees/payment-categories/');
}

export function listTaxGroups(): Promise<NamedRow[]> {
  return apiFetch<NamedRow[]>('/api/v1/fees/tax-groups/');
}
