import type { Metadata, Viewport } from 'next';
import { headers } from 'next/headers';

import { AppShell } from '@/components/app-shell';
import { AuthProvider } from '@/components/auth-provider';

import './globals.css';

export const metadata: Metadata = {
  title: { default: 'Grras LMS', template: '%s · Grras LMS' },
  description: 'Learning Management System — platform foundation.',
  // The app is authenticated and holds learner data; keep it out of indexes.
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

/**
 * Every route renders per request.
 *
 * The Content-Security-Policy in `middleware.ts` carries a nonce, and Next can
 * only put that nonce on its inline scripts while it is rendering the response.
 * A statically prerendered page was built long before the request existed, so
 * it carries no nonce, its inline bootstrap is refused, and the page loads
 * without ever hydrating — markup with no behaviour, which is worse than an
 * error because nothing reports it.
 *
 * The cost here is close to nothing: every page in this application is behind
 * authentication and fetches its data from the API in the browser, so there was
 * no meaningful static output to give up.
 */
export const dynamic = 'force-dynamic';

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Read so the nonce is definitely resolved for this request; Next matches it
  // against the CSP header itself when it emits its scripts.
  await headers();

  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
