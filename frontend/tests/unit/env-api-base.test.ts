/**
 * Where the browser is told to find the API.
 *
 * `NEXT_PUBLIC_API_BASE_URL` is baked in at build time and locally reads
 * `http://localhost:8000`. That is right for one visitor: someone on the same
 * machine who typed `localhost`. Open the same dev server as `127.0.0.1`, by
 * LAN address, or from a phone, and the page tells that browser to call its
 * own localhost — the API rejects the unlisted origin, and even once it is
 * allowed a cookie set on `localhost` is not sent from a page on `127.0.0.1`,
 * so sign-in appears to work and the next request is anonymous.
 *
 * These pin the rule that fixes it, and — more importantly — pin that it
 * cannot fire against a real deployment.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

async function baseUrlFrom({ configured, pageOrigin }: { configured: string; pageOrigin: string }) {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', configured);
  // `lib/env` reads the variable at module load, so the stub has to be in
  // place before the import rather than before the call.
  const { apiBaseUrl } = await import('@/lib/env');
  const url = new URL(pageOrigin);
  vi.stubGlobal('window', {
    location: { hostname: url.hostname, protocol: url.protocol, origin: url.origin },
  });
  return apiBaseUrl();
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('the API base URL in the browser', () => {
  it('is left alone when the page host already matches', async () => {
    expect(
      await baseUrlFrom({
        configured: 'http://localhost:8000',
        pageOrigin: 'http://localhost:3100',
      }),
    ).toBe('http://localhost:8000');
  });

  it('follows the page host when the page is on 127.0.0.1', async () => {
    expect(
      await baseUrlFrom({
        configured: 'http://localhost:8000',
        pageOrigin: 'http://127.0.0.1:3100',
      }),
    ).toBe('http://127.0.0.1:8000');
  });

  it('follows a LAN address, so a phone on the same network reaches the API', async () => {
    expect(
      await baseUrlFrom({
        configured: 'http://localhost:8000',
        pageOrigin: 'http://192.168.1.24:3100',
      }),
    ).toBe('http://192.168.1.24:8000');
  });

  it('keeps the API port rather than the page port', async () => {
    expect(
      await baseUrlFrom({
        configured: 'http://localhost:8000',
        pageOrigin: 'http://127.0.0.1:4321',
      }),
    ).toBe('http://127.0.0.1:8000');
  });

  it('never rewrites a real API hostname, whatever the page host is', async () => {
    // The guard that keeps this out of production: a deployment's API is not a
    // loopback name, so a page served from anywhere leaves it untouched.
    expect(
      await baseUrlFrom({
        configured: 'https://api.grras.example',
        pageOrigin: 'https://app.grras.example',
      }),
    ).toBe('https://api.grras.example');
  });

  it('leaves a malformed base alone rather than throwing on every request', async () => {
    expect(
      await baseUrlFrom({ configured: '/api-proxy', pageOrigin: 'http://127.0.0.1:3100' }),
    ).toBe('/api-proxy');
  });
});
