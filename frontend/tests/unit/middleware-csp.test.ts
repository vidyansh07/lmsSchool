/**
 * The Content-Security-Policy the middleware sets.
 *
 * Two things are worth pinning. The first is that the policy exists at all and
 * carries a per-request nonce, because that is what lets Next's inline
 * bootstrap run without `unsafe-inline` in production.
 *
 * The second is `upgrade-insecure-requests`, which has to be present in
 * production and absent in development. It rewrites every http subresource to
 * https. In front of a TLS terminator that is exactly right. On a development
 * machine served over plain http it upgrades same-origin URLs — the
 * authenticated profile-image route, for one — to a port with no TLS listener,
 * and the browser fails them with ERR_SSL_PROTOCOL_ERROR. That was a real
 * broken avatar, not a hypothetical.
 */

import { NextRequest } from 'next/server';
import { afterEach, describe, expect, it } from 'vitest';

import { middleware } from '@/middleware';

const ORIGINAL_ENV = process.env.NODE_ENV;

function policyFor(nodeEnv: string, pageUrl = 'http://localhost:3100/profile'): string {
  // `NODE_ENV` is read-only in the Next types but writable at runtime, and the
  // middleware branches on it, so this is the only way to exercise both paths.
  (process.env as Record<string, string>).NODE_ENV = nodeEnv;
  const response = middleware(new NextRequest(pageUrl));
  return response.headers.get('content-security-policy') ?? '';
}

function directive(policy: string, name: string): string {
  return policy.split('; ').find((part) => part.startsWith(`${name} `)) ?? '';
}

afterEach(() => {
  (process.env as Record<string, string>).NODE_ENV = ORIGINAL_ENV as string;
});

describe('the content security policy', () => {
  it('upgrades insecure requests in production', () => {
    expect(policyFor('production')).toContain('upgrade-insecure-requests');
  });

  it('does not upgrade them in development, where the app is served over http', () => {
    expect(policyFor('development')).not.toContain('upgrade-insecure-requests');
  });

  it('carries a nonce rather than allowing every inline script', () => {
    const policy = policyFor('production');

    expect(policy).toMatch(/script-src [^;]*'nonce-[^']+'/);
    expect(policy).not.toMatch(/script-src [^;]*'unsafe-inline'/);
    expect(policy).not.toMatch(/script-src [^;]*'unsafe-eval'/);
  });

  it('keeps the restrictive directives in both environments', () => {
    for (const environment of ['production', 'development']) {
      const policy = policyFor(environment);

      expect(policy).toContain("default-src 'self'");
      expect(policy).toContain("frame-ancestors 'none'");
      expect(policy).toContain("object-src 'none'");
      expect(policy).toContain("base-uri 'self'");
      expect(policy).toContain("form-action 'self'");
    }
  });

  it('allows images from the API origin, and only that origin', () => {
    const imgSrc = directive(policyFor('production'), 'img-src');

    // A profile photo is served by the backend under session auth, so `'self'`
    // alone would block it wherever the two are not behind one proxy.
    expect(imgSrc).toContain('http://localhost:8000');
    expect(imgSrc).not.toContain('*');
  });

  it('allows the API on the host the visitor actually used', () => {
    // `lib/env.ts` points the browser at the API on the page's own host, so a
    // policy naming only `localhost` blocks every call made from `127.0.0.1`
    // — which reads as "the frontend cannot see the backend".
    const connectSrc = directive(
      policyFor('development', 'http://192.168.1.24:3100/dashboard'),
      'connect-src',
    );

    expect(connectSrc).toContain('http://192.168.1.24:8000');
    expect(connectSrc).toContain('http://127.0.0.1:8000');
    expect(connectSrc).toContain('http://localhost:8000');
  });

  it('does not widen a real API origin to the page host', () => {
    (process.env as Record<string, string>).NEXT_PUBLIC_API_BASE_URL = 'https://api.grras.example';
    try {
      const connectSrc = directive(
        policyFor('production', 'https://app.grras.example/dashboard'),
        'connect-src',
      );

      expect(connectSrc).toBe("connect-src 'self' https://api.grras.example");
    } finally {
      delete (process.env as Record<string, string>).NEXT_PUBLIC_API_BASE_URL;
    }
  });

  it('never leaves an empty directive behind when one is filtered out', () => {
    expect(policyFor('development')).not.toMatch(/;\s*;|;\s*$/);
  });
});
