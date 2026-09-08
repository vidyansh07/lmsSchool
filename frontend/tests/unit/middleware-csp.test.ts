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

function policyFor(nodeEnv: string): string {
  // `NODE_ENV` is read-only in the Next types but writable at runtime, and the
  // middleware branches on it, so this is the only way to exercise both paths.
  (process.env as Record<string, string>).NODE_ENV = nodeEnv;
  const response = middleware(new NextRequest('http://localhost:3100/profile'));
  return response.headers.get('content-security-policy') ?? '';
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
    const policy = policyFor('production');
    const imgSrc = policy.split('; ').find((directive) => directive.startsWith('img-src '));

    // A profile photo is served by the backend under session auth, so `'self'`
    // alone would block it wherever the two are not behind one proxy.
    expect(imgSrc).toContain('http://localhost:8000');
    expect(imgSrc).not.toContain('*');
  });

  it('never leaves an empty directive behind when one is filtered out', () => {
    expect(policyFor('development')).not.toMatch(/;\s*;|;\s*$/);
  });
});
