import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiFetch, ensureCsrfToken } from '@/lib/api';

function mockFetch(response: Partial<Response> & { jsonBody?: unknown }) {
  const body = response.jsonBody === undefined ? '' : JSON.stringify(response.jsonBody);
  const fetchMock = vi.fn().mockResolvedValue({
    ok: response.ok ?? true,
    status: response.status ?? 200,
    headers: new Headers(response.headers),
    text: async () => body,
  } as Response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('apiFetch', () => {
  it('returns the parsed body on success', async () => {
    mockFetch({ jsonBody: { status: 'ok' } });
    await expect(apiFetch<{ status: string }>('/health/ready/')).resolves.toEqual({ status: 'ok' });
  });

  it('always sends credentials so the session cookie travels cross-origin', async () => {
    const fetchMock = mockFetch({ jsonBody: {} });
    await apiFetch('/api/v1/auth/me/');
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: 'include' });
  });

  it('converts the error envelope into a typed ApiError', async () => {
    mockFetch({
      ok: false,
      status: 403,
      jsonBody: {
        error: { code: 'permission_denied', message: 'Nope.', request_id: 'req-1' },
      },
    });

    await expect(apiFetch('/api/v1/users/')).rejects.toMatchObject({
      status: 403,
      code: 'permission_denied',
      message: 'Nope.',
      requestId: 'req-1',
    });
  });

  it('reports a network failure without leaking the underlying error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED 10.0.0.1:8000')));
    const error = await apiFetch('/health/ready/').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).not.toContain('ECONNREFUSED');
  });

  it('sends the CSRF header on unsafe methods when the cookie is present', async () => {
    document.cookie = 'grras_csrftoken=token-value';
    const fetchMock = mockFetch({ jsonBody: {} });
    await apiFetch('/api/v1/auth/login/', { method: 'POST', body: { email: 'a@b.test' } });
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get('X-CSRFToken')).toBe('token-value');
  });

  it('does not send a CSRF header on safe methods', async () => {
    document.cookie = 'grras_csrftoken=token-value';
    const fetchMock = mockFetch({ jsonBody: {} });
    await apiFetch('/api/v1/auth/me/');
    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get('X-CSRFToken')).toBeNull();
  });

  it('flags authentication failures so callers can redirect to sign-in', async () => {
    mockFetch({
      ok: false,
      status: 401,
      jsonBody: {
        error: { code: 'authentication_required', message: 'Sign in.', request_id: 'r' },
      },
    });
    const error = (await apiFetch('/api/v1/auth/me/').catch((cause) => cause)) as ApiError;
    expect(error.isAuthError).toBe(true);
  });
});

describe('ensureCsrfToken', () => {
  it('fetches a token only when the cookie is missing', async () => {
    const fetchMock = mockFetch({ jsonBody: { detail: 'CSRF cookie set.' } });
    await ensureCsrfToken();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    document.cookie = 'grras_csrftoken=already-here';
    await ensureCsrfToken();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('CSRF token rotation', () => {
  /**
   * Django rotates the CSRF token when a session begins or ends, so the cookie
   * held from before a sign-out is no longer the one the server expects — and
   * because *a* cookie is present, nothing prompts a refresh. The symptom is
   * specific: sign out, sign back in, and the first action fails once.
   */
  function respond(status: number, body: unknown) {
    return {
      ok: status < 400,
      status,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: async () => JSON.stringify(body),
    } as Response;
  }

  it('refreshes the token and retries once when the server rejects a stale one', async () => {
    document.cookie = 'grras_csrftoken=stale-token';
    const calls: string[] = [];

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        calls.push(url);
        if (url.includes('/auth/csrf/')) {
          document.cookie = 'grras_csrftoken=fresh-token';
          return respond(200, { detail: 'ok' });
        }
        const writes = calls.filter((entry) => entry.includes('/things/')).length;
        if (writes > 1) return respond(200, { ok: true });
        return respond(403, {
          error: { code: 'csrf_failed', message: 'CSRF verification failed.', request_id: 'r1' },
        });
      }),
    );

    const { apiMutate } = await import('@/lib/api');
    await expect(apiMutate('/api/v1/things/', { method: 'POST' })).resolves.toEqual({ ok: true });

    expect(calls.filter((entry) => entry.includes('/auth/csrf/'))).toHaveLength(1);
    expect(calls.filter((entry) => entry.includes('/things/'))).toHaveLength(2);
  });

  it('does not retry a refusal that is not a CSRF failure', async () => {
    document.cookie = 'grras_csrftoken=good-token';
    const calls: string[] = [];

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        calls.push(String(input));
        return respond(403, {
          error: { code: 'permission_denied', message: 'Not allowed.', request_id: 'r2' },
        });
      }),
    );

    const { apiMutate } = await import('@/lib/api');
    await expect(apiMutate('/api/v1/things/', { method: 'POST' })).rejects.toBeInstanceOf(ApiError);
    expect(calls.filter((entry) => entry.includes('/things/'))).toHaveLength(1);
  });
});
