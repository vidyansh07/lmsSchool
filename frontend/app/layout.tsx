import type { Metadata, Viewport } from 'next';

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
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
