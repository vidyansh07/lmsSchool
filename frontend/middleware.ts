import { NextResponse, type NextRequest } from 'next/server';

/**
 * Content-Security-Policy, with a per-request nonce.
 *
 * Why this is middleware and not a static header
 * ----------------------------------------------
 * Next's App Router serves the page with inline `<script>` elements — the
 * bootstrap and the streamed flight data. A policy of `script-src 'self'`
 * blocks them, and blocking them means React never hydrates: the markup
 * renders, no handler is attached, and every form on the site silently does
 * nothing. That is not a subtle degradation, and it does not show up in
 * development, where the policy carries `'unsafe-inline'`.
 *
 * The two honest options are `'unsafe-inline'` — which is not a policy, since
 * an injected inline script is exactly what CSP exists to stop — or a nonce
 * minted per request. This is the nonce.
 *
 * `'strict-dynamic'` is deliberately absent. It tells the browser to ignore the
 * host allowlist entirely and trust only what a nonced script loads — which
 * sounds stronger and, here, breaks the page: Next's bundle chunks are ordinary
 * `<script src>` tags that carry no nonce of their own, so with
 * `'strict-dynamic'` every one of them is refused. `'self'` plus a nonce keeps
 * both halves working: same-origin bundles load because they are same-origin,
 * and an injected inline script is still refused because it cannot guess the
 * nonce. Injected inline script is the attack CSP is for.
 *
 * The nonce reaches the renderer through the `x-nonce` request header, which is
 * where Next looks for it.
 */
export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
  const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
  const isDevelopment = process.env.NODE_ENV === 'development';

  const policy = [
    "default-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    // The API origin is listed because authenticated media — a profile photo —
    // is served by the backend, not by Next, and is a different origin whenever
    // the two are not behind one proxy. Only the configured origin is allowed;
    // this is not `img-src *`.
    `img-src 'self' data: blob: ${apiOrigin}`,
    "font-src 'self' data:",
    // Next inlines critical CSS, and there is no nonce path for it.
    "style-src 'self' 'unsafe-inline'",
    isDevelopment
      ? // The dev server rebuilds and evaluates modules in the browser.
        `script-src 'self' 'nonce-${nonce}' 'unsafe-inline' 'unsafe-eval'`
      : `script-src 'self' 'nonce-${nonce}'`,
    `connect-src 'self' ${apiOrigin}`,
    // Production only. The directive rewrites every http subresource to https,
    // which is right in front of a TLS terminator and wrong on a development
    // machine served over plain http: the browser upgrades same-origin URLs
    // like the authenticated profile-image route to a port with no TLS listener and
    // the request dies as ERR_SSL_PROTOCOL_ERROR. Shipping it in development
    // buys nothing — there is no downgrade to prevent on loopback — and breaks
    // images that work in production.
    isDevelopment ? null : 'upgrade-insecure-requests',
  ]
    .filter((directive): directive is string => directive !== null)
    .join('; ');

  const headers = new Headers(request.headers);
  headers.set('x-nonce', nonce);
  headers.set('content-security-policy', policy);

  const response = NextResponse.next({ request: { headers } });
  response.headers.set('content-security-policy', policy);
  return response;
}

export const config = {
  matcher: [
    /*
     * Every page, and nothing that is already an immutable static asset:
     * hashed bundles, images and the favicon carry no inline script, and
     * minting a nonce for each of them is work with no reader.
     */
    {
      source: '/((?!_next/static|_next/image|favicon.ico).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
