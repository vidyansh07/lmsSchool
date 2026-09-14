/**
 * API calls for centres (`/api/v1/branches/`).
 *
 * A branch bounds people and classes — who a manager may see and which
 * classes appear on their screens. It is not a tenant: the course catalogue
 * and the academic rules are shared across every centre.
 */

import { apiFetch, apiMutate, queryString } from './api';
import type { AdminUser, Branch, Paginated } from '@/types/api';

export async function listBranches(
  query: { page?: number; page_size?: number; search?: string } = {},
): Promise<Paginated<Branch>> {
  return apiFetch<Paginated<Branch>>(`/api/v1/branches/${queryString(query)}`);
}

export async function createBranch(payload: {
  code: string;
  name: string;
  city?: string;
}): Promise<Branch> {
  return apiMutate<Branch>('/api/v1/branches/', { method: 'POST', body: payload });
}

export async function updateBranch(
  id: string,
  changes: Partial<{ code: string; name: string; city: string }>,
): Promise<Branch> {
  return apiMutate<Branch>(`/api/v1/branches/${id}/`, { method: 'PATCH', body: changes });
}

/** Move an account to another centre. Audited as its own action server-side. */
export async function moveUserToBranch(
  userId: string,
  branchId: string,
  reason = '',
): Promise<AdminUser> {
  return apiMutate<AdminUser>(`/api/v1/users/${userId}/branch/`, {
    method: 'POST',
    body: { branch_id: branchId, reason },
  });
}
