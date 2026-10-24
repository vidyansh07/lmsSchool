/**
 * The reference lists the payment dialog picks from: banks, payment
 * categories, tax groups.
 *
 * All three are an administrator's lists rather than enums, because every
 * institute's are different and none of them is a code change. Each has at
 * most one default, which is what the dialog opens with.
 */

import { apiFetch, apiMutate } from './api';

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

/** What the settings screen sends for any of these three lists. A bank has
 *  no default; the serializer ignores the flag it does not have. */
export interface NamedRowInput {
  name: string;
  is_default?: boolean;
  is_active?: boolean;
}

export function createBank(payload: NamedRowInput): Promise<NamedRow> {
  return apiMutate<NamedRow>('/api/v1/banks/', { method: 'POST', body: payload });
}

export function updateBank(id: string, payload: Partial<NamedRowInput>): Promise<NamedRow> {
  return apiMutate<NamedRow>(`/api/v1/banks/${id}/`, { method: 'PATCH', body: payload });
}

export function createPaymentCategory(payload: NamedRowInput): Promise<NamedRow> {
  return apiMutate<NamedRow>('/api/v1/fees/payment-categories/', {
    method: 'POST',
    body: payload,
  });
}

export function updatePaymentCategory(
  id: string,
  payload: Partial<NamedRowInput>,
): Promise<NamedRow> {
  return apiMutate<NamedRow>(`/api/v1/fees/payment-categories/${id}/`, {
    method: 'PATCH',
    body: payload,
  });
}

export function createTaxGroup(payload: NamedRowInput): Promise<NamedRow> {
  return apiMutate<NamedRow>('/api/v1/fees/tax-groups/', { method: 'POST', body: payload });
}

export function updateTaxGroup(id: string, payload: Partial<NamedRowInput>): Promise<NamedRow> {
  return apiMutate<NamedRow>(`/api/v1/fees/tax-groups/${id}/`, { method: 'PATCH', body: payload });
}
