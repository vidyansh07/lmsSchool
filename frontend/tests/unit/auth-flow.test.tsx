import { describe, expect, it, vi, afterEach } from 'vitest';

import { apiMutate } from '@/lib/api';
import { changePassword, login, requestPasswordReset } from '@/lib/auth';

function mockFetch(status = 200, body: unknown = {}) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    headers: new Headers(),
    text: async () => JSON.stringify(body),
  } as Response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('auth calls', () => {
  it('fetches a CSRF token before an unsafe request', async () => {
    document.cookie = '';
    const fetchMock = mockFetch(200, { detail: 'CSRF cookie set.' });
    await apiMutate('/api/v1/auth/logout/', { method: 'POST' });

    // First call is the CSRF handshake, second is the actual mutation.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v1/auth/csrf/');
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/v1/auth/logout/');
  });

  it('never puts credentials in the URL', async () => {
    document.cookie = 'grras_csrftoken=token';
    const fetchMock = mockFetch(200, { email: 'a@b.test' });
    await login('a@b.test', 'super-secret-password');

    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).not.toContain('super-secret-password');
    expect(url).not.toContain('a@b.test');
  });

  it('sends password changes as a JSON body, not query parameters', async () => {
    document.cookie = 'grras_csrftoken=token';
    const fetchMock = mockFetch(200, { detail: 'Password changed.' });
    await changePassword('old-password-value', 'new-password-value');

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe('http://localhost:8000/api/v1/auth/password/change/');
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({
      current_password: 'old-password-value',
      new_password: 'new-password-value',
    });
  });

  it('surfaces the generic reset response without interpreting it', async () => {
    document.cookie = 'grras_csrftoken=token';
    mockFetch(202, { detail: 'If an account exists for that address, a link has been sent.' });
    const response = await requestPasswordReset('anyone@example.test');
    expect(response.detail).toContain('If an account exists');
  });
});
