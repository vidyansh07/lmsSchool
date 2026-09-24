import type { Metadata, Viewport } from 'next';
import { Inter, Sora } from 'next/font/google';
import { headers } from 'next/headers';

import { AppShell } from '@/components/app-shell';
import { AuthProvider } from '@/components/auth-provider';

import { BrandTheme } from '@/components/brand-theme';
import { Toaster, ToastProvider } from '@/components/ui/toast';

import './globals.css';

/**
 * Two families, both self-hosted by Next rather than fetched from Google at
 * runtime.
 *
 * Inter carries everything a person reads at length -- tables, forms, body
 * copy -- because it was built for interfaces at small sizes and has a real
 * tabular-figure set, which a gradebook and a ledger both depend on.
 *
 * Sora carries the headings and the KPI figures. At this density the type
 * scale cannot afford large size jumps to signal hierarchy, so hierarchy
 * comes from the family change instead: a heading is a different voice, not
 * a bigger one. `globals.css` wires it to `--font-heading` and applies it to
 * `h1`-`h4` in the base layer, so a screen gets it without asking.
 *
 * Self-hosting matters twice over: the Content-Security-Policy in
 * `middleware.ts` sets `font-src 'self' data:` and allows no third-party font
 * origin, so a Google Fonts URL would yield unstyled text in production and
 * nowhere else; and a webfont fetched on first paint is the classic cause of
 * text appearing a beat late. `display: swap` shows the fallback immediately
 * and replaces it, rather than holding blank text while it waits.
 */
const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
});

const sora = Sora({
  subsets: ['latin'],
  // Only the weight the headings actually use. Each extra weight is another
  // font file on the wire for a hierarchy that is already legible.
  weight: ['600'],
  display: 'swap',
  variable: '--font-sora',
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
    <html lang="en" className={`${inter.variable} ${sora.variable}`}>
      <body className="font-sans antialiased">
        <BrandTheme />
        {/* Outside `AppShell` so a toast survives a route change and is not
            clipped by the shell's own scroll container — a confirmation that
            disappears with the screen that caused it has confirmed nothing. */}
        <ToastProvider>
          <AuthProvider>
            <AppShell>{children}</AppShell>
          </AuthProvider>
          <Toaster />
        </ToastProvider>
      </body>
    </html>
  );
}
