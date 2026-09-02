/**
 * Authentication calls.
 *
 * How browser authentication works, end to end:
 *
 * 1. `GET /api/v1/auth/csrf/` sets a readable `grras_csrftoken` cookie.
 * 2. `POST /api/v1/auth/login/` echoes that token in `X-CSRFToken` and, on
 *    success, the server sets an HttpOnly session cookie.
 * 3. Every later request carries the session cookie automatically
 *    (`credentials: 'include'`); unsafe methods keep sending `X-CSRFToken`.
 * 4. Signing out clears the session server-side.
 *
 * The session cookie is never readable from JavaScript, so this module cannot
 * inspect or forge it — which is the point. "Am I signed in?" is answered by
 * calling `/auth/me/`, not by reading local state.
 */

import { apiFetch, apiMutate } from './api';
import type { CurrentUser, DetailResponse } from '@/types/api';

export async function login(email: string, password: string): Promise<CurrentUser> {
  return apiMutate<CurrentUser>('/api/v1/auth/login/', {
    method: 'POST',
    body: { email, password },
  });
}

export async function logout(): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/logout/', { method: 'POST' });
}

export async function logoutEverywhere(): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/logout-all/', { method: 'POST' });
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>('/api/v1/auth/me/');
}

export async function updateCurrentUser(
  changes: Partial<Pick<CurrentUser, 'first_name' | 'last_name' | 'phone'>>,
): Promise<CurrentUser> {
  return apiMutate<CurrentUser>('/api/v1/auth/me/', { method: 'PATCH', body: changes });
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/password/change/', {
    method: 'POST',
    body: { current_password: currentPassword, new_password: newPassword },
  });
}

export async function requestPasswordReset(email: string): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/password/reset/', {
    method: 'POST',
    body: { email },
  });
}

export async function confirmPasswordReset(
  token: string,
  newPassword: string,
): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/password/reset/confirm/', {
    method: 'POST',
    body: { token, new_password: newPassword },
  });
}

export async function requestEmailVerification(): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/email/verify/', { method: 'POST' });
}

export async function confirmEmailVerification(token: string): Promise<DetailResponse> {
  return apiMutate<DetailResponse>('/api/v1/auth/email/verify/confirm/', {
    method: 'POST',
    body: { token },
  });
}

export async function uploadProfileImage(file: File): Promise<CurrentUser> {
  const formData = new FormData();
  formData.append('image', file);
  return apiMutate<CurrentUser>('/api/v1/auth/me/profile-image/', {
    method: 'POST',
    formData,
  });
}

export async function removeProfileImage(): Promise<CurrentUser> {
  return apiMutate<CurrentUser>('/api/v1/auth/me/profile-image/', { method: 'DELETE' });
}
