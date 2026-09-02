import type { NextConfig } from 'next';

/**
 * Security headers are set here as well as on the API.
 *
 * The two may be independent origins in production, so neither can rely on the
 * other's headers. `standalone` output keeps the production image small.
 */
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'X-Frame-Options', value: 'DENY' },
  {
    key: 'Permissions-Policy',
    value: 'geolocation=(), microphone=(), camera=(), interest-cohort=()',
  },
];

/**
 * The Content-Security-Policy is NOT here. It needs a per-request nonce, which a
 * static header cannot carry, so `middleware.ts` owns it — see the reasoning
 * there. Setting a second policy in this file would not relax the first one:
 * browsers apply every policy they are given and take the intersection, so a
 * leftover `script-src 'self'` here would keep blocking the nonced scripts and
 * the page would stay dead for a reason nothing points at.
 */

const nextConfig: NextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          ...securityHeaders,
        ],
      },
    ];
  },
};

export default nextConfig;
