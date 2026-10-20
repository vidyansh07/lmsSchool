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

/**
 * Told when the server answers `authentication_required` — the session cookie
 * expired, was revoked from another device, or a role change ended it.
 * `AuthProvider` listens, so a screen open across the 12-hour session limit
 * goes back to sign-in instead of showing "Authentication is required." with
 * a Retry that can never work.
 */
const sessionEndedListeners = new Set<() => void>();

export function onSessionEnded(listener: () => void): () => void {
  sessionEndedListeners.add(listener);
  return () => {
    sessionEndedListeners.delete(listener);
  };
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Abort the request after this many milliseconds. */
  timeoutMs?: number;
  /** Send as multipart/form-data instead of JSON (file uploads). */
  formData?: FormData;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  // 20 s (22a). A slow report or export is cut off with a message and a Retry
  // rather than a spinner that never resolves. `signal` is the *caller's* own
  // cancellation (a superseded request key, an unmounted component) — pulled
  // out of `rest` so it is not spread straight into `fetch`'s options, where
  // it would just be overwritten by the timeout controller's signal below.
  // Both need to be able to abort the one request, so the external signal is
  // wired onto the internal controller instead of replacing it.
  const { body, formData, timeoutMs = 20_000, headers, signal: externalSignal, ...rest } = options;
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
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  // Fold the caller's own cancellation into the same controller that owns the
  // timeout, so either one can abort this one underlying request.
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

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
    if (aborted && !timedOut) {
      // The caller cancelled deliberately (a stale request key, an unmounted
      // component) rather than the request failing — nothing went wrong, so
      // this is not an error a screen should ever show. `code: 'cancelled'`
      // lets a caller that inspects the rejection tell the two apart; `useApi`
      // and `useList` already drop a superseded response via their own
      // `cancelled` flag before this would even be inspected.
      throw new ApiError(0, 'cancelled', '', '');
    }
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
    const error = new ApiError(
      response.status,
      envelope?.error?.code ?? 'error',
      envelope?.error?.message ?? 'The request failed.',
      envelope?.error?.request_id ?? response.headers.get('X-Request-ID') ?? '',
      envelope?.error?.details ?? null,
    );
    if (error.isAuthError) sessionEndedListeners.forEach((listener) => listener());
    throw error;
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
  // A throttle's details are a number of seconds, not a field: reported as
  // `retry_after_seconds: "57.3"` it would read as a validation message.
  const throttled = rateLimitMessage(error);
  if (throttled) return { __all__: throttled };
  const details = error.details as unknown;
  if (!details || typeof details !== 'object' || Array.isArray(details)) {
    return { __all__: error.message };
  }
  const mapped = mapDetails(details as Record<string, unknown>);
  if (Object.keys(mapped).length === 0) mapped.__all__ = error.message;
  return mapped;
}

/**
 * Flatten DRF's error shapes onto the names a form reads.
 *
 * `non_field_errors` is the form-level message, so it becomes `__all__`. A
 * nested serializer (`{"profile": {"skills": [...]}}`) lifts its fields to the
 * top so a form that renders `errors.skills` sees them, and keeps the parent
 * key as well. A list of row errors (`[{}, {"amount": [...]}]`) contributes
 * its first sentence. The first message for a key wins.
 */
function mapDetails(details: Record<string, unknown>): Record<string, string> {
  const mapped: Record<string, string> = {};
  for (const [field, value] of Object.entries(details)) {
    const key = field === 'non_field_errors' ? '__all__' : field;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      for (const [inner, message] of Object.entries(mapDetails(value as Record<string, unknown>))) {
        mapped[inner === '__all__' ? key : inner] ??= message;
      }
    }
    const message = firstMessage(value);
    if (message !== null) mapped[key] ??= message;
  }
  return mapped;
}

function firstMessage(value: unknown): string | null {
  if (typeof value === 'string') return value || null;
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = firstMessage(item);
      if (message !== null) return message;
    }
    return null;
  }
  if (value && typeof value === 'object') return firstMessage(Object.values(value));
  return null;
}

/**
 * The sentence a form shows above its fields: the form-level message, or else
 * the first error under a key the form does not render beside a field. A 403,
 * a 409 on `status` or a timeout otherwise leaves the button reverting with
 * nothing said.
 */
export function unshownError(
  fields: Record<string, string>,
  shown: readonly string[],
): string | null {
  if (fields.__all__) return fields.__all__;
  const stray = Object.entries(fields).find(([key]) => !shown.includes(key));
  return stray ? stray[1] : null;
}

/**
 * True when a write may have reached the server although no answer came
 * back — a timeout or a dropped connection. Retrying blindly can record a
 * payment twice; the screen should say to check first.
 */
export function isUncertainOutcome(cause: unknown): boolean {
  return cause instanceof ApiError && (cause.code === 'timeout' || cause.code === 'network_error');
}

/** A friendly sentence for a `429 rate_limited` refusal, or `null` otherwise. */
export function rateLimitMessage(cause: unknown): string | null {
  if (!(cause instanceof ApiError) || cause.code !== 'rate_limited') return null;
  const raw = cause.details?.retry_after_seconds;
  const seconds = Number(Array.isArray(raw) ? raw[0] : raw);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return 'Too many attempts. Wait a moment and try again.';
  }
  const wait = Math.ceil(seconds);
  return `Too many attempts. Wait ${wait} second${wait === 1 ? '' : 's'} and try again.`;
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
