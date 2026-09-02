/**
 * The single place the frontend talks to the backend.
 *
 * Responsibilities:
 *  - resolve the right base URL for the current execution context
 *  - send session cookies (`credentials: 'include'`) and the CSRF header
 *  - turn the backend's error envelope into a typed `ApiError`
 *
 * Deliberately *not* responsible for authorization decisions. The UI may hide
 * what a user cannot use, but every protected resource is re-checked by the
 * backend; nothing here is a security control.
 */

import { apiBaseUrl } from './env';
import type { ApiErrorBody } from '@/types/api';

const CSRF_COOKIE_NAME = 'grras_csrftoken';
const CSRF_HEADER_NAME = 'X-CSRFToken';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly details?: Record<string, string[] | string> | null;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string,
    details?: Record<string, string[] | string> | null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  /** True when signing in (or signing in again) would resolve the failure. */
  get isAuthError(): boolean {
    return this.status === 401 || this.code === 'authentication_required';
  }
}

function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${CSRF_COOKIE_NAME}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE_NAME.length + 1)) : null;
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Abort the request after this many milliseconds. */
  timeoutMs?: number;
  /** Send as multipart/form-data instead of JSON (file uploads). */
  formData?: FormData;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, formData, timeoutMs = 15_000, headers, ...rest } = options;
  const method = (rest.method ?? 'GET').toUpperCase();

  const requestHeaders = new Headers(headers);
  requestHeaders.set('Accept', 'application/json');
  // Content-Type is set by the browser for FormData so the multipart boundary
  // is correct; setting it by hand would break the upload.
  if (body !== undefined) requestHeaders.set('Content-Type', 'application/json');

  if (UNSAFE_METHODS.has(method)) {
    const token = readCsrfCookie();
    if (token) requestHeaders.set(CSRF_HEADER_NAME, token);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...rest,
      method,
      headers: requestHeaders,
      // Session cookies are the credential; they must travel cross-origin.
      credentials: 'include',
      cache: 'no-store',
      signal: controller.signal,
      body: formData ?? (body === undefined ? undefined : JSON.stringify(body)),
    });
  } catch (cause) {
    const aborted = cause instanceof DOMException && cause.name === 'AbortError';
    throw new ApiError(
      0,
      aborted ? 'timeout' : 'network_error',
      aborted
        ? 'The request timed out. Check your connection and try again.'
        : 'Could not reach the server. Check your connection and try again.',
      '',
    );
  } finally {
    clearTimeout(timeout);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload: unknown = text ? safeParse(text) : null;

  if (!response.ok) {
    const envelope = payload as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      envelope?.error?.code ?? 'error',
      envelope?.error?.message ?? 'The request failed.',
      envelope?.error?.request_id ?? response.headers.get('X-Request-ID') ?? '',
      envelope?.error?.details ?? null,
    );
  }

  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Fetch a CSRF cookie before the first unsafe request of a session. */
export async function ensureCsrfToken({ force = false } = {}): Promise<void> {
  if (!force && readCsrfCookie()) return;
  await apiFetch<{ detail: string }>('/api/v1/auth/csrf/');
}

/**
 * Perform an unsafe request, fetching a CSRF token first if one is missing.
 *
 * Every mutation in the app goes through here, so no call site can forget the
 * token handshake.
 *
 * A stale token is retried once. Django rotates the CSRF token when a session
 * begins or ends, so the cookie held from before a sign-out is no longer the
 * one the server expects — and because a cookie *is* present, the check above
 * has no reason to fetch a new one. The symptom is specific and maddening:
 * sign out, sign back in, and the first action fails once for no visible
 * reason, then works. One forced refresh and one retry removes it. Only a
 * `csrf_failed` is retried, and only once, so a genuine refusal is still a
 * refusal.
 */
export async function apiMutate<T>(
  path: string,
  options: RequestOptions & { method: string },
): Promise<T> {
  await ensureCsrfToken();
  try {
    return await apiFetch<T>(path, options);
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'csrf_failed') {
      await ensureCsrfToken({ force: true });
      return apiFetch<T>(path, options);
    }
    throw cause;
  }
}

/**
 * Turn an `ApiError` into a map of field name to message.
 *
 * The backend returns field errors in `error.details`; anything else becomes a
 * form-level message under `__all__`.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) {
    return { __all__: 'Something went wrong. Please try again.' };
  }
  const details = error.details;
  if (!details || typeof details !== 'object') {
    return { __all__: error.message };
  }
  const mapped: Record<string, string> = {};
  for (const [field, value] of Object.entries(details)) {
    mapped[field] = Array.isArray(value) ? String(value[0]) : String(value);
  }
  if (Object.keys(mapped).length === 0) mapped.__all__ = error.message;
  return mapped;
}

/**
 * The most specific sentence an error carries.
 *
 * The envelope's `message` is deliberately generic for a validation failure
 * ("The submitted data is invalid."), which is useless on its own. The field
 * details hold what actually went wrong, so prefer the first of those.
 */
export function errorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  const mapped = fieldErrors(error);
  const specific = Object.entries(mapped).find(([field]) => field !== '__all__');
  if (specific) return specific[1];
  return mapped.__all__ ?? fallback;
}

/** Build a query string, omitting empty values. */
export function queryString(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value));
    }
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}
