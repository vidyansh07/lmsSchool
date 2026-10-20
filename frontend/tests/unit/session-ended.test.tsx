/**
 * A session that ends under an open screen (the 12-hour limit, a revoke from
 * another device, a role change) used to leave every page saying
 * "Authentication is required." with a Retry that could never work. Any
 * `authentication_required` answer while signed in now forgets the user, so
 * `RequireAuth` sends them to sign-in, which says why.
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider, useAuth } from '@/components/auth-provider';
import { apiFetch } from '@/lib/api';

function respond(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(),
    text: () => Promise.resolve(JSON.stringify(body)),
  };
}

function Probe() {
  const { user, isLoading, sessionEnded } = useAuth();
  if (isLoading) return <p>loading</p>;
  return (
    <p>
      {user ? `signed in as ${user.email}` : 'signed out'}
      {sessionEnded ? ' · session ended' : ''}
    </p>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('session ended under an open screen', () => {
  it('forgets the user when any request says the session is gone', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(respond(200, { id: 'u1', email: 'asha@example.com', capabilities: [] }))
      .mockResolvedValue(
        respond(403, {
          error: { code: 'authentication_required', message: 'Authentication is required.', request_id: 'r' },
        }),
      );
    vi.stubGlobal('fetch', fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(
      await screen.findByText('signed in as asha@example.com', undefined, { timeout: 5000 }),
    ).toBeInTheDocument();

    await act(async () => {
      await apiFetch('/api/v1/students/').catch(() => undefined);
    });

    await waitFor(() => expect(screen.getByText('signed out · session ended')).toBeInTheDocument(), {
      timeout: 5000,
    });
  });

  it('does not call a visitor who was never signed in "session ended"', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        respond(403, {
          error: { code: 'authentication_required', message: 'Authentication is required.', request_id: 'r' },
        }),
      ),
    );
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(await screen.findByText('signed out', undefined, { timeout: 5000 })).toBeInTheDocument();
  });
});
