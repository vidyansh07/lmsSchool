import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import { headers } from 'next/headers';

import { AppShell } from '@/components/app-shell';
import { AuthProvider } from '@/components/auth-provider';

import { BrandTheme } from '@/components/brand-theme';
import { MotionProvider } from '@/components/ui/motion';
import { Toaster, ToastProvider } from '@/components/ui/toast';

import './globals.css';

/**
 * Inter, self-hosted by Next rather than fetched from Google at runtime.
 *
 * It is what grras.com uses, so the ERP and the public site read as one
 * organisation. Self-hosting matters twice over here: the Content-Security-
 * Policy in `middleware.ts` does not allow a third-party font origin, and a
 * webfont fetched on first paint is the classic cause of text appearing a
 * beat late. `display: swap` means the fallback shows immediately and is
 * replaced, rather than the page holding blank text while it waits.
 */
const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

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
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        <BrandTheme />
        {/* Outside `AppShell` so a toast survives a route change and is not
            clipped by the shell's own scroll container — a confirmation that
            disappears with the screen that caused it has confirmed nothing. */}
        <ToastProvider>
          <AuthProvider>
            {/* Loads the animation runtime once for the whole tree. Inside
                `AuthProvider` because nothing on the sign-in screen animates
                beyond what CSS already does, and outside `AppShell` so the
                shell's own transitions can use it too. */}
            <MotionProvider>
              <AppShell>{children}</AppShell>
            </MotionProvider>
          </AuthProvider>
          <Toaster />
        </ToastProvider>
      </body>
    </html>
  );
}
